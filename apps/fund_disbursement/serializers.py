from django.db.models import Max
from rest_framework import serializers

from apps.fund_disbursement.models import (
    DisbursementRecord,
    EvidenceFile,
    EvidenceRequirementType,
    EvidenceSubmission,
    Fund,
    Installment,
    KPIResult,
    Milestone,
    MilestoneEvidenceRequirement,
    MilestoneKPI,
    ReviewDecision,
)


class EvidenceRequirementTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenceRequirementType
        fields = ("id", "organization", "label", "description", "is_active")
        read_only_fields = ("id", "organization")


class MilestoneKPISerializer(serializers.ModelSerializer):
    class Meta:
        model = MilestoneKPI
        fields = (
            "id",
            "name",
            "metric_type",
            "comparator",
            "target_value",
            "target_value_max",
            "target_text",
            "unit",
            "display_order",
        )
        read_only_fields = ("id",)


class MilestoneEvidenceRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = MilestoneEvidenceRequirement
        fields = ("id", "requirement_type", "label", "is_mandatory", "display_order")
        read_only_fields = ("id",)


class InstallmentMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Installment
        fields = ("id", "installment_no", "amount", "currency", "status", "approved_at", "disbursed_at")
        read_only_fields = fields


class MilestoneSerializer(serializers.ModelSerializer):
    kpis = MilestoneKPISerializer(many=True, required=False)
    evidence_requirements = MilestoneEvidenceRequirementSerializer(many=True, required=False)
    installment = InstallmentMiniSerializer(read_only=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, write_only=True)
    currency = serializers.CharField(max_length=3, write_only=True, required=False, default="USD")

    class Meta:
        model = Milestone
        fields = (
            "id",
            "fund",
            "sequence_position",
            "title",
            "deliverable_description",
            "due_date",
            "unlocks_after_milestone",
            "status",
            "kpis",
            "evidence_requirements",
            "installment",
            "amount",
            "currency",
        )
        read_only_fields = ("id", "fund", "status")

    def validate_unlocks_after_milestone(self, value):
        fund = self.context.get("fund") or getattr(self.instance, "fund", None)
        if value is not None and fund is not None and value.fund_id != fund.id:
            raise serializers.ValidationError("Must be a milestone in the same fund.")
        return value

    def create(self, validated_data):
        kpis = validated_data.pop("kpis", [])
        evidence_requirements = validated_data.pop("evidence_requirements", [])
        amount = validated_data.pop("amount")
        currency = validated_data.pop("currency", "USD")

        milestone = Milestone.objects.create(**validated_data)

        fund = milestone.fund
        next_no = (fund.installments.aggregate(n=Max("installment_no"))["n"] or 0) + 1
        Installment.objects.create(
            fund=fund,
            milestone=milestone,
            installment_no=next_no,
            amount=amount,
            currency=currency,
        )

        MilestoneKPI.objects.bulk_create([MilestoneKPI(milestone=milestone, **k) for k in kpis])
        MilestoneEvidenceRequirement.objects.bulk_create(
            [MilestoneEvidenceRequirement(milestone=milestone, **r) for r in evidence_requirements]
        )
        return milestone

    def update(self, instance, validated_data):
        validated_data.pop("amount", None)
        validated_data.pop("currency", None)
        kpis = validated_data.pop("kpis", None)
        evidence_requirements = validated_data.pop("evidence_requirements", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if kpis is not None:
            instance.kpis.all().delete()
            MilestoneKPI.objects.bulk_create([MilestoneKPI(milestone=instance, **k) for k in kpis])
        if evidence_requirements is not None:
            instance.evidence_requirements.all().delete()
            MilestoneEvidenceRequirement.objects.bulk_create(
                [MilestoneEvidenceRequirement(milestone=instance, **r) for r in evidence_requirements]
            )
        return instance


class MilestoneMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ("id", "title", "sequence_position", "status")
        read_only_fields = fields


class FundListSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(source="recipient.name", read_only=True)
    milestone_count = serializers.IntegerField(read_only=True, default=0)
    disbursed_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, default=0
    )

    class Meta:
        model = Fund
        fields = (
            "id",
            "organization",
            "recipient",
            "recipient_name",
            "title",
            "funding_type",
            "total_amount",
            "currency",
            "lifecycle_status",
            "health_status",
            "milestone_count",
            "disbursed_total",
            "start_date",
            "end_date",
            "created_at",
        )
        read_only_fields = ("id", "lifecycle_status", "health_status", "created_at")


class FundSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(source="recipient.name", read_only=True)

    class Meta:
        model = Fund
        fields = (
            "id",
            "organization",
            "recipient",
            "recipient_name",
            "agreement_reference",
            "title",
            "funding_type",
            "total_amount",
            "currency",
            "start_date",
            "end_date",
            "sequencing",
            "lifecycle_status",
            "health_status",
            "linked_report",
            "notes",
            "activated_at",
            "completed_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "organization",
            "lifecycle_status",
            "activated_at",
            "completed_at",
            "created_at",
        )

    def validate(self, attrs):
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        recipient = attrs.get("recipient") or getattr(self.instance, "recipient", None)
        if recipient is not None and organization is not None and recipient.organization_id != organization.id:
            raise serializers.ValidationError({"recipient": "Recipient must belong to the same organization."})
        return attrs


class FundLifecycleSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("active", "completed", "cancelled", "suspended"))


class InstallmentSerializer(serializers.ModelSerializer):
    milestone = MilestoneMiniSerializer(read_only=True)

    class Meta:
        model = Installment
        fields = (
            "id",
            "fund",
            "milestone",
            "installment_no",
            "amount",
            "currency",
            "status",
            "unlocked_at",
            "approved_at",
            "disbursed_at",
            "approved_by",
        )
        read_only_fields = fields


class EvidenceFileSerializer(serializers.ModelSerializer):
    file_name = serializers.CharField(source="file.original_filename", read_only=True, default="")
    file_size = serializers.IntegerField(source="file.size_bytes", read_only=True, default=None)

    class Meta:
        model = EvidenceFile
        fields = ("id", "external_url", "file_name", "file_size", "requirement", "uploaded_at")
        read_only_fields = ("id", "uploaded_at")


class KPIResultSerializer(serializers.ModelSerializer):
    kpi_name = serializers.CharField(source="milestone_kpi.name", read_only=True)

    class Meta:
        model = KPIResult
        fields = (
            "id",
            "milestone_kpi",
            "kpi_name",
            "reported_value",
            "reported_text",
            "meets_target",
            "reviewer_note",
        )
        read_only_fields = ("id",)


class EvidenceSubmissionSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.full_name", read_only=True, default="")
    files = EvidenceFileSerializer(many=True, read_only=True)
    kpi_results = KPIResultSerializer(many=True, read_only=True)

    class Meta:
        model = EvidenceSubmission
        fields = (
            "id",
            "installment",
            "milestone",
            "attempt_no",
            "submitted_by",
            "submitted_by_name",
            "respondent_note",
            "status",
            "submitted_at",
            "reviewed_at",
            "files",
            "kpi_results",
        )
        read_only_fields = fields


class SubmitEvidenceFileInputSerializer(serializers.Serializer):
    external_url = serializers.URLField()
    requirement = serializers.UUIDField(required=False, allow_null=True, default=None)


class SubmitEvidenceKpiResultInputSerializer(serializers.Serializer):
    milestone_kpi = serializers.UUIDField()
    reported_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    reported_text = serializers.CharField(required=False, allow_blank=True, default="")


class SubmitEvidenceSerializer(serializers.Serializer):
    respondent_note = serializers.CharField(required=False, allow_blank=True, default="")
    files = SubmitEvidenceFileInputSerializer(many=True, required=False, default=list)
    kpi_results = SubmitEvidenceKpiResultInputSerializer(many=True, required=False, default=list)


class ReviewDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewDecision
        fields = (
            "id",
            "submission",
            "installment",
            "reviewer_user",
            "reviewer_name",
            "decision",
            "comment",
            "decided_at",
        )
        read_only_fields = fields


class DecideSubmissionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=("approved", "rejected", "info_requested"))
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class DisbursementRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisbursementRecord
        fields = (
            "id",
            "installment",
            "amount_paid",
            "currency",
            "fx_rate_to_fund_ccy",
            "payment_reference",
            "payment_method",
            "paid_at",
            "recorded_by",
            "note",
        )
        read_only_fields = ("id", "recorded_by")


class RecordDisbursementSerializer(serializers.Serializer):
    amount_paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default="")
    fx_rate_to_fund_ccy = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    payment_reference = serializers.CharField(required=False, allow_blank=True, default="")
    payment_method = serializers.ChoiceField(
        choices=("bank_transfer", "mobile_money", "cheque", "cash", "other"),
        required=False,
        allow_blank=True,
        default="",
    )
    paid_at = serializers.DateTimeField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ReviewQueueItemSerializer(serializers.ModelSerializer):
    fund_id = serializers.UUIDField(source="fund.id", read_only=True)
    fund_title = serializers.CharField(source="fund.title", read_only=True)
    recipient_name = serializers.CharField(source="fund.recipient.name", read_only=True)
    milestone = MilestoneMiniSerializer(read_only=True)
    latest_submission = serializers.SerializerMethodField()

    class Meta:
        model = Installment
        fields = (
            "id",
            "fund_id",
            "fund_title",
            "recipient_name",
            "milestone",
            "installment_no",
            "amount",
            "currency",
            "status",
            "unlocked_at",
            "latest_submission",
        )
        read_only_fields = fields

    def get_latest_submission(self, installment):
        submission = installment.submissions.order_by("-attempt_no").first()
        if submission is None:
            return None
        return {
            "id": str(submission.id),
            "attempt_no": submission.attempt_no,
            "status": submission.status,
            "submitted_at": submission.submitted_at,
        }
