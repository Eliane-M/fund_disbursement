from rest_framework import serializers

from apps.maturity_assessment.models import (
    Assessment,
    AssessmentInvitation,
    Capability,
    Category,
    MaturityBand,
    Question,
    QuestionNumericRule,
    QuestionOption,
    Recommendation,
    Report,
    ReportGap,
    ReportShareStatus,
    Response,
    ScoreResult,
    SubCapability,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "id",
            "organization",
            "name",
            "description",
            "auto_share_reports",
            "is_archived",
            "created_at",
        )
        read_only_fields = ("id", "organization", "created_at")


class AssessmentListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    respondent_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Assessment
        fields = (
            "id",
            "organization",
            "category",
            "category_name",
            "name",
            "version_label",
            "respondent_type",
            "status",
            "respondent_count",
            "published_at",
            "created_at",
        )
        read_only_fields = ("id", "published_at", "created_at")


class AssessmentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Assessment
        fields = (
            "id",
            "organization",
            "category",
            "category_name",
            "name",
            "version_label",
            "description",
            "respondent_type",
            "status",
            "gap_threshold_pct",
            "auto_share_reports",
            "default_target_score",
            "current_version",
            "published_at",
            "archived_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "organization",
            "status",
            "current_version",
            "published_at",
            "archived_at",
            "created_at",
        )


class SubCapabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCapability
        fields = ("id", "capability", "name", "description", "display_order", "is_archived", "created_at")
        read_only_fields = ("id", "capability", "created_at")


class CapabilitySerializer(serializers.ModelSerializer):
    sub_capabilities = SubCapabilitySerializer(many=True, read_only=True)

    class Meta:
        model = Capability
        fields = (
            "id",
            "assessment",
            "name",
            "description",
            "weight_pct",
            "target_score",
            "display_order",
            "is_archived",
            "sub_capabilities",
            "created_at",
        )
        read_only_fields = ("id", "assessment", "created_at")


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ("id", "label", "score_value", "likert_position", "display_order")
        read_only_fields = ("id",)


class QuestionNumericRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionNumericRule
        fields = ("id", "min_value", "max_value", "score_value", "display_order")
        read_only_fields = ("id",)


class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, required=False)
    numeric_rules = QuestionNumericRuleSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = (
            "id",
            "assessment",
            "capability",
            "sub_capability",
            "question_text",
            "help_text",
            "question_type",
            "is_required",
            "is_scored",
            "allow_not_applicable",
            "max_points",
            "numeric_unit",
            "numeric_min",
            "numeric_max",
            "display_order",
            "page_no",
            "is_archived",
            "options",
            "numeric_rules",
        )
        read_only_fields = ("id", "assessment")

    def validate(self, attrs):
        capability = attrs.get("capability") or getattr(self.instance, "capability", None)
        assessment = getattr(self.instance, "assessment", None) or self.context.get("assessment")
        # An explicit null clears the sub-capability, so absence and None must be told
        # apart here — otherwise a PATCH moving a question to another capability while
        # clearing its sub would re-check the stale sub and reject a valid edit.
        if "sub_capability" in attrs:
            sub_capability = attrs["sub_capability"]
        else:
            sub_capability = getattr(self.instance, "sub_capability", None)
        if capability is not None and assessment is not None and capability.assessment_id != assessment.id:
            raise serializers.ValidationError({"capability": "Capability must belong to the same assessment."})
        if sub_capability is not None and capability is not None and sub_capability.capability_id != capability.id:
            raise serializers.ValidationError(
                {"sub_capability": "Sub-capability must belong to the stated capability."}
            )
        return attrs

    def create(self, validated_data):
        options = validated_data.pop("options", [])
        numeric_rules = validated_data.pop("numeric_rules", [])
        question = Question.objects.create(**validated_data)
        self._sync_children(question, options, numeric_rules)
        return question

    def update(self, instance, validated_data):
        options = validated_data.pop("options", None)
        numeric_rules = validated_data.pop("numeric_rules", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        self._sync_children(instance, options, numeric_rules)
        return instance

    def _sync_children(self, question, options, numeric_rules):
        if options is not None:
            question.options.all().delete()
            QuestionOption.objects.bulk_create(
                [QuestionOption(question=question, **option) for option in options]
            )
        if numeric_rules is not None:
            question.numeric_rules.all().delete()
            QuestionNumericRule.objects.bulk_create(
                [QuestionNumericRule(question=question, **rule) for rule in numeric_rules]
            )


class MaturityBandSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaturityBand
        fields = ("id", "assessment", "label", "min_score", "max_score", "color_hex", "display_order")
        read_only_fields = ("id", "assessment")


class RecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recommendation
        fields = ("id", "assessment", "capability", "band", "recommendation_text", "display_order")
        read_only_fields = ("id", "assessment", "capability")


class InvitationRespondentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class AssessmentInvitationSerializer(serializers.ModelSerializer):
    respondent_name = serializers.CharField(source="respondent.name", read_only=True)

    class Meta:
        model = AssessmentInvitation
        fields = (
            "id",
            "organization",
            "assessment",
            "assessment_version",
            "respondent",
            "respondent_name",
            "status",
            "due_date",
            "sent_at",
            "started_at",
            "submitted_at",
            "reminder_count",
            "expires_at",
        )
        read_only_fields = (
            "id",
            "organization",
            "assessment",
            "assessment_version",
            "status",
            "sent_at",
            "started_at",
            "submitted_at",
            "reminder_count",
        )


class ScoreResultSerializer(serializers.ModelSerializer):
    capability_name = serializers.CharField(source="capability.name", read_only=True)

    class Meta:
        model = ScoreResult
        fields = (
            "capability",
            "capability_name",
            "sub_capability",
            "score_pct",
            "score_10",
            "weight_pct",
            "target_score",
            "is_gap",
        )


class ReportGapSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportGap
        fields = ("id", "capability", "capability_name", "score_pct", "recommendation_text", "display_order")


class ReportListSerializer(serializers.ModelSerializer):
    respondent_name = serializers.CharField(source="respondent.name", read_only=True)
    category_name = serializers.CharField(source="respondent.category.name", read_only=True, default="")

    class Meta:
        model = Report
        fields = (
            "id",
            "respondent",
            "respondent_name",
            "category_name",
            "overall_score",
            "maturity_band_label",
            "share_status",
            "generated_at",
        )


class ReportDetailSerializer(serializers.ModelSerializer):
    respondent_name = serializers.CharField(source="respondent.name", read_only=True)
    category_name = serializers.CharField(source="respondent.category.name", read_only=True, default="")
    submitted_at = serializers.DateTimeField(source="invitation.submitted_at", read_only=True)
    capability_scores = serializers.SerializerMethodField()
    gaps = ReportGapSerializer(many=True, read_only=True)

    class Meta:
        model = Report
        fields = (
            "id",
            "organization",
            "respondent",
            "respondent_name",
            "category_name",
            "overall_score",
            "maturity_band_label",
            "share_status",
            "share_token",
            "submitted_at",
            "generated_at",
            "capability_scores",
            "gaps",
        )
        read_only_fields = fields

    def get_capability_scores(self, report):
        results = ScoreResult.objects.filter(
            invitation_id=report.invitation_id, sub_capability__isnull=True
        ).select_related("capability")
        return ScoreResultSerializer(results, many=True).data


class ReportShareUpdateSerializer(serializers.Serializer):
    share_status = serializers.ChoiceField(choices=("draft", "shared", "withheld"))


# --- Respondent-facing ("my") serializers --------------------------------
#
# Deliberately narrower than the admin serializers: no access_token, no
# reviewer notes, and a report only surfaces once an admin has shared it.


class MyInvitationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    assessment_name = serializers.CharField(source="assessment.name", read_only=True)
    assessment_version_label = serializers.CharField(source="assessment.version_label", read_only=True)
    category_name = serializers.CharField(source="assessment.category.name", read_only=True, default="")
    respondent_name = serializers.CharField(source="respondent.name", read_only=True)
    report = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentInvitation
        fields = (
            "id",
            "organization",
            "organization_name",
            "assessment",
            "assessment_name",
            "assessment_version_label",
            "category_name",
            "respondent",
            "respondent_name",
            "status",
            "due_date",
            "sent_at",
            "started_at",
            "submitted_at",
            "created_at",
            "report",
        )

    def get_report(self, invitation):
        report = getattr(invitation, "report", None)
        if report is None or report.share_status != ReportShareStatus.SHARED:
            return None
        return {
            "id": str(report.id),
            "overall_score": str(report.overall_score),
            "maturity_band_label": report.maturity_band_label,
            "shared_at": report.shared_at,
        }


class MyReportDetailSerializer(ReportDetailSerializer):
    """Full shared report for the respondent: scores, gaps and recommendations,
    but none of the sharing controls (token/status) the org uses."""

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    assessment_name = serializers.CharField(source="invitation.assessment.name", read_only=True, default="")
    shared_at = serializers.DateTimeField(read_only=True)

    class Meta(ReportDetailSerializer.Meta):
        fields = tuple(
            f for f in ReportDetailSerializer.Meta.fields if f not in ("share_token", "share_status")
        ) + ("organization_name", "assessment_name", "shared_at")
        read_only_fields = fields


class MyReportSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    respondent_name = serializers.CharField(source="respondent.name", read_only=True)
    assessment_name = serializers.CharField(source="invitation.assessment.name", read_only=True, default="")
    category_name = serializers.CharField(source="respondent.category.name", read_only=True, default="")
    submitted_at = serializers.DateTimeField(source="invitation.submitted_at", read_only=True)

    class Meta:
        model = Report
        fields = (
            "id",
            "organization",
            "organization_name",
            "respondent",
            "respondent_name",
            "assessment_name",
            "category_name",
            "overall_score",
            "maturity_band_label",
            "submitted_at",
            "shared_at",
            "generated_at",
        )


# --- Filling in an assessment --------------------------------------------


class QuestionnaireOptionSerializer(serializers.ModelSerializer):
    """Options as the respondent sees them — score values are deliberately hidden."""

    class Meta:
        model = QuestionOption
        fields = ("id", "label", "likert_position", "display_order")


class QuestionnaireQuestionSerializer(serializers.ModelSerializer):
    options = QuestionnaireOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = (
            "id",
            "capability",
            "sub_capability",
            "question_text",
            "help_text",
            "question_type",
            "is_required",
            "allow_not_applicable",
            "numeric_unit",
            "numeric_min",
            "numeric_max",
            "display_order",
            "page_no",
            "options",
        )


class MyResponseSerializer(serializers.ModelSerializer):
    selected_options = serializers.SerializerMethodField()

    class Meta:
        model = Response
        fields = ("question", "answer_value", "is_not_applicable", "selected_options", "answered_at")

    def get_selected_options(self, response):
        return [str(selection.question_option_id) for selection in response.selected_options.all()]


class AnswerInputSerializer(serializers.Serializer):
    question = serializers.UUIDField()
    answer_value = serializers.JSONField(required=False, allow_null=True)
    selected_options = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    is_not_applicable = serializers.BooleanField(required=False, default=False)


class SaveAnswersSerializer(serializers.Serializer):
    answers = AnswerInputSerializer(many=True)


class GradeResponseSerializer(serializers.Serializer):
    reviewer_score = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)


class PendingResponseSerializer(serializers.ModelSerializer):
    """A free-text answer waiting for a reviewer to assign points."""

    question_text = serializers.CharField(source="question.question_text", read_only=True)
    capability_name = serializers.CharField(source="question.capability.name", read_only=True)
    max_points = serializers.DecimalField(
        source="question.max_points", max_digits=6, decimal_places=2, read_only=True
    )
    respondent_name = serializers.CharField(source="invitation.respondent.name", read_only=True)
    assessment_name = serializers.CharField(source="invitation.assessment.name", read_only=True)
    is_scored = serializers.BooleanField(source="question.is_scored", read_only=True)

    class Meta:
        model = Response
        fields = (
            "id",
            "invitation",
            "question",
            "question_text",
            "is_scored",
            "capability_name",
            "respondent_name",
            "assessment_name",
            "answer_value",
            "max_points",
            "reviewer_score",
            "reviewed_at",
            "answered_at",
        )


class ReviewQueueItemSerializer(serializers.ModelSerializer):
    respondent_name = serializers.CharField(source="respondent.name", read_only=True)
    assessment_name = serializers.CharField(source="assessment.name", read_only=True)
    pending_review = serializers.IntegerField(read_only=True)
    free_text_count = serializers.IntegerField(read_only=True, default=0)
    report_id = serializers.SerializerMethodField()
    overall_score = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentInvitation
        fields = (
            "id",
            "organization",
            "assessment",
            "assessment_name",
            "respondent",
            "respondent_name",
            "status",
            "submitted_at",
            "pending_review",
            "free_text_count",
            "report_id",
            "overall_score",
        )

    def get_report_id(self, invitation):
        report = getattr(invitation, "report", None)
        return str(report.id) if report else None

    def get_overall_score(self, invitation):
        report = getattr(invitation, "report", None)
        return str(report.overall_score) if report else None
