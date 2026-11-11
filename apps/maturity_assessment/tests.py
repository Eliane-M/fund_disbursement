from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import MembershipRole, MembershipStatus, OrganizationMembership, User
from apps.core.models import Notification, Organization, Respondent
from apps.maturity_assessment import services
from apps.maturity_assessment.models import (
    Assessment,
    AssessmentStatus,
    Capability,
    Category,
    InvitationStatus,
    MaturityBand,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
    Report,
    Response,
    ScoreResult,
    SubCapability,
)

TEST_MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


class InlineThread:
    """Runs the submission email inline so the assertion is not racing a thread."""

    def __init__(self, target=None, **kwargs):
        self._target = target

    def start(self):
        # The real thread closes its own DB connections when it finishes. Run
        # inline, that would close the test's connection (a no-op on in-memory
        # SQLite, fatal on Postgres), so neutralise it here.
        with patch("apps.maturity_assessment.services.connections"):
            self._target()


@override_settings(MAILERS=TEST_MAILERS)
class RespondentSubmissionTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Ridgeline", slug="ridgeline")
        self.admin = User.objects.create_user(email="admin@example.com", password="pw-admin-12345")
        self.reviewer = User.objects.create_user(email="reviewer@example.com", password="pw-review-12345")
        self.respondent_user = User.objects.create_user(email="grantee@example.com", password="pw-grantee-1234")
        self.other_user = User.objects.create_user(email="other@example.com", password="pw-other-12345")

        self.respondent = Respondent.objects.create(
            organization=self.organization, name="Amara Foods", primary_contact_email="amara@example.com"
        )
        self.other_respondent = Respondent.objects.create(
            organization=self.organization, name="Rival Co", primary_contact_email="rival@example.com"
        )
        for user, role, respondent in (
            (self.admin, MembershipRole.ORG_ADMIN, None),
            (self.reviewer, MembershipRole.REVIEWER, None),
            (self.respondent_user, MembershipRole.RESPONDENT, self.respondent),
            (self.other_user, MembershipRole.RESPONDENT, self.other_respondent),
        ):
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=user,
                role=role,
                respondent=respondent,
                status=MembershipStatus.ACTIVE,
            )

        category = Category.objects.create(organization=self.organization, name="Agritech")
        self.assessment = Assessment.objects.create(
            organization=self.organization, category=category, name="Readiness", version_label="v1"
        )
        # Two capabilities, equally weighted, so the overall score is a clean average.
        self.finance = Capability.objects.create(
            assessment=self.assessment, name="Finance", weight_pct=50, target_score=75
        )
        self.ops = Capability.objects.create(
            assessment=self.assessment, name="Operations", weight_pct=50, target_score=75
        )
        self.bookkeeping = SubCapability.objects.create(capability=self.finance, name="Bookkeeping")

        self.yes_no = Question.objects.create(
            assessment=self.assessment,
            capability=self.finance,
            sub_capability=self.bookkeeping,
            question_text="Do you keep monthly books?",
            question_type=QuestionType.YES_NO,
            max_points=10,
        )
        QuestionOption.objects.create(question=self.yes_no, label="Yes", score_value=10, display_order=0)
        self.no_option = QuestionOption.objects.create(
            question=self.yes_no, label="No", score_value=0, display_order=1
        )
        self.yes_option = self.yes_no.options.get(label="Yes")

        self.numeric = Question.objects.create(
            assessment=self.assessment,
            capability=self.ops,
            question_text="Tonnes processed per month",
            question_type=QuestionType.NUMERIC,
            max_points=10,
            numeric_min=0,
            numeric_max=100,
        )
        self.free_text = Question.objects.create(
            assessment=self.assessment,
            capability=self.ops,
            question_text="Describe your quality process",
            question_type=QuestionType.FREE_TEXT,
            max_points=10,
            is_scored=True,
            is_required=False,
        )

        MaturityBand.objects.create(assessment=self.assessment, label="Emerging", min_score=0, max_score=49)
        MaturityBand.objects.create(assessment=self.assessment, label="Established", min_score=50, max_score=100)
        Recommendation.objects.create(
            assessment=self.assessment, capability=self.ops, recommendation_text="Tighten operations."
        )

        services.publish_assessment(self.assessment, self.admin)
        self.assessment.refresh_from_db()
        self.invitation = services.create_invitation(self.assessment, self.respondent, self.admin)
        mail.outbox.clear()

        self.client = APIClient()
        self.client.force_authenticate(self.respondent_user)

    def _answer_all(self, yes=True, numeric="50", free_text="We inspect every batch."):
        return self.client.put(
            f"/api/assessment/my/assessments/{self.invitation.id}/answers/",
            {
                "answers": [
                    {
                        "question": str(self.yes_no.id),
                        "selected_options": [str(self.yes_option.id if yes else self.no_option.id)],
                    },
                    {"question": str(self.numeric.id), "answer_value": numeric},
                    {"question": str(self.free_text.id), "answer_value": free_text},
                ]
            },
            format="json",
        )

    def test_questionnaire_hides_option_scores(self):
        response = self.client.get(f"/api/assessment/my/assessments/{self.invitation.id}/")
        self.assertEqual(response.status_code, 200)
        option = response.data["questions"][0]["options"][0]
        self.assertNotIn("score_value", option)

    def test_saving_answers_marks_in_progress(self):
        self.assertEqual(self._answer_all().status_code, 200)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, InvitationStatus.IN_PROGRESS)
        self.assertIsNotNone(self.invitation.started_at)
        self.assertEqual(Response.objects.filter(invitation=self.invitation).count(), 3)

    def test_saving_answers_is_idempotent(self):
        self._answer_all(yes=True)
        self._answer_all(yes=False)
        answer = Response.objects.get(invitation=self.invitation, question=self.yes_no)
        self.assertEqual(answer.selected_options.count(), 1)
        self.assertEqual(answer.selected_options.first().question_option.label, "No")

    def test_submit_scores_report_and_notifies_reviewers(self):
        self._answer_all()
        # reviewers are told only once the submission commits, and the email is
        # delivered off-thread so the respondent is not kept waiting on SMTP
        with patch("apps.maturity_assessment.services.threading.Thread", InlineThread):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/assessment/my/assessments/{self.invitation.id}/submit/"
                )
        self.assertEqual(response.status_code, 201, response.data)
        # free text is not auto-scored, so it is pending and excluded from the total
        self.assertEqual(response.data["pending_review"], 1)

        report = Report.objects.get(invitation=self.invitation)
        # Finance 10/10 = 100%, Operations numeric 50/100 of 10 points = 50%.
        # Equal weights -> (100 + 50) / 2 = 75.
        self.assertEqual(report.overall_score, Decimal("75.00"))
        self.assertEqual(report.maturity_band_label, "Established")
        self.assertEqual(report.share_status, "draft")

        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, InvitationStatus.SUBMITTED)
        self.assertIsNotNone(self.invitation.submitted_at)

        rollups = ScoreResult.objects.filter(invitation=self.invitation, sub_capability__isnull=True)
        self.assertEqual(rollups.count(), 2)
        self.assertEqual(rollups.get(capability=self.finance).score_pct, Decimal("100.00"))
        self.assertEqual(rollups.get(capability=self.ops).score_pct, Decimal("50.00"))
        # the sub-capability breakdown is kept alongside the roll-up
        self.assertTrue(
            ScoreResult.objects.filter(invitation=self.invitation, sub_capability=self.bookkeeping).exists()
        )

        # Operations is below its 75 target, so it lands in the report as a gap
        gap = report.gaps.get()
        self.assertEqual(gap.capability_name, "Operations")
        self.assertEqual(gap.recommendation_text, "Tighten operations.")

        # every reviewer and org admin is told, in-app and by email
        recipients = set(
            Notification.objects.filter(template_key="assessment.submitted").values_list(
                "recipient_email", flat=True
            )
        )
        self.assertEqual(recipients, {"admin@example.com", "reviewer@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Amara Foods", mail.outbox[0].subject)
        self.assertCountEqual(mail.outbox[0].to, ["admin@example.com", "reviewer@example.com"])

    def test_required_answers_are_enforced(self):
        self.client.put(
            f"/api/assessment/my/assessments/{self.invitation.id}/answers/",
            {"answers": [{"question": str(self.numeric.id), "answer_value": "10"}]},
            format="json",
        )
        response = self.client.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Report.objects.filter(invitation=self.invitation).exists())

    def test_submitting_twice_is_rejected(self):
        self._answer_all()
        self.client.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/")
        again = self.client.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/")
        self.assertEqual(again.status_code, 400)

    def test_grading_free_text_recomputes_the_report(self):
        self._answer_all()
        self.client.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/")
        answer = Response.objects.get(invitation=self.invitation, question=self.free_text)

        reviewer_client = APIClient()
        reviewer_client.force_authenticate(self.reviewer)
        response = reviewer_client.post(
            f"/api/assessment/responses/{answer.id}/score/", {"reviewer_score": "10"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["pending_review"], 0)

        report = Report.objects.get(invitation=self.invitation)
        # Operations now has numeric 5/10 plus free text 10/10 = 75%.
        # (100 + 75) / 2 = 87.5
        self.assertEqual(report.overall_score, Decimal("87.50"))
        self.assertFalse(report.gaps.exists())

    def test_reviewer_cannot_exceed_max_points(self):
        self._answer_all()
        self.client.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/")
        answer = Response.objects.get(invitation=self.invitation, question=self.free_text)
        reviewer_client = APIClient()
        reviewer_client.force_authenticate(self.reviewer)
        response = reviewer_client.post(
            f"/api/assessment/responses/{answer.id}/score/", {"reviewer_score": "999"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_respondents_cannot_touch_another_respondents_invitation(self):
        other = APIClient()
        other.force_authenticate(self.other_user)
        self.assertEqual(
            other.get(f"/api/assessment/my/assessments/{self.invitation.id}/").status_code, 404
        )
        self.assertEqual(
            other.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/").status_code, 404
        )

    def test_respondents_cannot_use_the_reviewer_endpoints(self):
        self._answer_all()
        self.client.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/")
        answer = Response.objects.get(invitation=self.invitation, question=self.free_text)
        self.assertEqual(
            self.client.get(
                f"/api/assessment/review-queue/?organization={self.organization.id}"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/assessment/responses/{answer.id}/score/", {"reviewer_score": "5"}, format="json"
            ).status_code,
            403,
        )

    def test_review_queue_lists_pending_work(self):
        self._answer_all()
        self.client.post(f"/api/assessment/my/assessments/{self.invitation.id}/submit/")
        reviewer_client = APIClient()
        reviewer_client.force_authenticate(self.reviewer)
        response = reviewer_client.get(
            f"/api/assessment/review-queue/?organization={self.organization.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["pending_review"], 1)
        self.assertEqual(response.data[0]["overall_score"], "75.00")
