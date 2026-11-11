"""Scoring engine: turns a respondent's answers into ScoreResults and a Report.

Auto-scorable question types are computed from the answer itself. Scored
free-text answers are never auto-scored — they sit pending until a reviewer
assigns points, and are excluded from the totals until then, so a fresh report
is never dragged down by work nobody has graded yet.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.maturity_assessment.models import (
    MaturityBand,
    Question,
    QuestionType,
    Recommendation,
    Report,
    ReportGap,
    ReportShareStatus,
    ScoreResult,
)

ZERO = Decimal("0")


def score_response(response):
    """(earned, max_points) for one answer, or (None, max_points) when it still
    needs a human. (None, 0) means the answer doesn't count toward any total."""
    question = response.question
    max_points = Decimal(question.max_points)

    if not question.is_scored or question.is_archived:
        return ZERO, ZERO
    if response.is_not_applicable:
        return ZERO, ZERO

    if question.question_type == QuestionType.FREE_TEXT:
        if response.reviewer_score is None:
            return None, max_points
        return min(Decimal(response.reviewer_score), max_points), max_points

    if question.question_type in (QuestionType.YES_NO, QuestionType.SINGLE_SELECT, QuestionType.LIKERT_5):
        option = next(iter(response.selected_options.all()), None)
        earned = Decimal(option.question_option.score_value) if option else ZERO
        return max(min(earned, max_points), ZERO), max_points

    if question.question_type == QuestionType.MULTI_SELECT:
        earned = sum(
            (Decimal(selection.question_option.score_value) for selection in response.selected_options.all()),
            ZERO,
        )
        return max(min(earned, max_points), ZERO), max_points

    if question.question_type == QuestionType.NUMERIC:
        value = _as_decimal(response.answer_value)
        if value is None:
            return ZERO, max_points
        rules = list(question.numeric_rules.all())
        for rule in rules:
            if Decimal(rule.min_value) <= value <= Decimal(rule.max_value):
                return max(min(Decimal(rule.score_value), max_points), ZERO), max_points
        if rules:
            return ZERO, max_points
        return _interpolate(question, value, max_points), max_points

    return ZERO, max_points


def _as_decimal(answer_value):
    if isinstance(answer_value, dict):
        answer_value = answer_value.get("value")
    if answer_value is None or answer_value == "":
        return None
    try:
        return Decimal(str(answer_value))
    except (ArithmeticError, ValueError):
        return None


def _interpolate(question, value, max_points):
    """No banding rules configured: scale linearly across the allowed range."""
    low = Decimal(question.numeric_min) if question.numeric_min is not None else ZERO
    high = Decimal(question.numeric_max) if question.numeric_max is not None else None
    if high is None or high <= low:
        return ZERO
    clamped = max(min(value, high), low)
    return ((clamped - low) / (high - low) * max_points).quantize(Decimal("0.01"))


def _bucket_key(question):
    return (question.capability_id, question.sub_capability_id)


@transaction.atomic
def compute_scores(invitation):
    """Rebuild this invitation's ScoreResult rows. Returns the overall score."""
    responses = (
        invitation.responses.select_related("question", "question__capability")
        .prefetch_related("selected_options__question_option", "question__numeric_rules")
        .all()
    )

    buckets = {}
    pending_review = 0
    for response in responses:
        earned, max_points = score_response(response)
        if max_points == ZERO:
            continue
        if earned is None:
            pending_review += 1
            continue
        key = _bucket_key(response.question)
        bucket = buckets.setdefault(key, {"raw": ZERO, "max": ZERO, "count": 0})
        bucket["raw"] += earned
        bucket["max"] += max_points
        bucket["count"] += 1

    capabilities = {
        cap.id: cap
        for cap in invitation.assessment.capabilities.filter(is_archived=False)
    }

    invitation.score_results.all().delete()
    rollups = {}
    rows = []
    for (capability_id, sub_capability_id), bucket in buckets.items():
        capability = capabilities.get(capability_id)
        if capability is None:
            continue
        rollup = rollups.setdefault(capability_id, {"raw": ZERO, "max": ZERO, "count": 0})
        rollup["raw"] += bucket["raw"]
        rollup["max"] += bucket["max"]
        rollup["count"] += bucket["count"]
        if sub_capability_id is None:
            continue
        score_pct = _percent(bucket["raw"], bucket["max"])
        rows.append(
            ScoreResult(
                invitation=invitation,
                capability=capability,
                sub_capability_id=sub_capability_id,
                questions_scored=bucket["count"],
                raw_points=bucket["raw"],
                max_points=bucket["max"],
                score_pct=score_pct,
                score_10=(score_pct / 10).quantize(Decimal("0.01")),
                weight_pct=capability.weight_pct,
                target_score=capability.target_score,
                is_gap=_is_gap(score_pct, capability.target_score),
            )
        )

    weighted_total = ZERO
    weight_total = ZERO
    unweighted = []
    for capability_id, rollup in rollups.items():
        capability = capabilities[capability_id]
        score_pct = _percent(rollup["raw"], rollup["max"])
        weight = Decimal(capability.weight_pct or 0)
        weighted_points = (score_pct * weight / 100).quantize(Decimal("0.01"))
        weighted_total += weighted_points
        weight_total += weight
        unweighted.append(score_pct)
        rows.append(
            ScoreResult(
                invitation=invitation,
                capability=capability,
                sub_capability=None,
                questions_scored=rollup["count"],
                raw_points=rollup["raw"],
                max_points=rollup["max"],
                score_pct=score_pct,
                score_10=(score_pct / 10).quantize(Decimal("0.01")),
                weight_pct=capability.weight_pct,
                weighted_points=weighted_points,
                target_score=capability.target_score,
                is_gap=_is_gap(score_pct, capability.target_score),
            )
        )

    ScoreResult.objects.bulk_create(rows)

    if weight_total > ZERO:
        overall = (weighted_total / weight_total * 100).quantize(Decimal("0.01"))
    elif unweighted:
        overall = (sum(unweighted, ZERO) / len(unweighted)).quantize(Decimal("0.01"))
    else:
        overall = ZERO
    return min(overall, Decimal("100.00")), pending_review


def _percent(raw, maximum):
    if maximum <= ZERO:
        return ZERO
    return (raw / maximum * 100).quantize(Decimal("0.01"))


def _is_gap(score_pct, target_score):
    return target_score is not None and score_pct < Decimal(target_score)


@transaction.atomic
def generate_report(invitation):
    """Create or refresh this invitation's report from its current scores."""
    overall, pending_review = compute_scores(invitation)
    assessment = invitation.assessment
    band = MaturityBand.objects.resolve(assessment.id, overall)

    report, _ = Report.objects.update_or_create(
        invitation=invitation,
        defaults={
            "organization": invitation.organization,
            "respondent": invitation.respondent,
            "assessment_version": invitation.assessment_version,
            "overall_score": overall,
            "maturity_band": band,
            "maturity_band_label": band.label if band else "",
        },
    )
    if report.share_status == "":
        report.share_status = ReportShareStatus.DRAFT
        report.save(update_fields=["share_status"])

    report.gaps.all().delete()
    gaps = []
    for index, result in enumerate(
        invitation.score_results.filter(sub_capability__isnull=True, is_gap=True)
        .select_related("capability")
        .order_by("score_pct")
    ):
        gaps.append(
            ReportGap(
                report=report,
                capability=result.capability,
                capability_name=result.capability.name,
                score_pct=result.score_pct or ZERO,
                recommendation_text=_recommendation_for(result.capability, band),
                display_order=index,
            )
        )
    ReportGap.objects.bulk_create(gaps)
    return report, pending_review


def _recommendation_for(capability, band):
    """Band-specific advice when it exists, else the capability's generic gap text."""
    recommendation = None
    if band is not None:
        recommendation = Recommendation.objects.filter(capability=capability, band=band).first()
    if recommendation is None:
        recommendation = Recommendation.objects.filter(capability=capability, band__isnull=True).first()
    return recommendation.recommendation_text if recommendation else ""


def pending_review_count(invitation):
    return sum(
        1
        for response in invitation.responses.select_related("question")
        if response.needs_review
    )


def grade_response(response, reviewer_score, reviewer):
    """Assign points to a free-text answer, then refresh the report."""
    response.reviewer_score = reviewer_score
    response.reviewed_by = reviewer
    response.reviewed_at = timezone.now()
    response.save(update_fields=["reviewer_score", "reviewed_by", "reviewed_at"])
    report, pending = generate_report(response.invitation)
    return response, report, pending


def unanswered_required_questions(invitation):
    answered = set(invitation.responses.values_list("question_id", flat=True))
    return [
        question
        for question in Question.objects.filter(
            assessment_id=invitation.assessment_id, is_archived=False, is_required=True
        )
        if question.id not in answered
    ]
