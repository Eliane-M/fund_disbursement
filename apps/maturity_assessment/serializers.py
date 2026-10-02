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
        sub_capability = attrs.get("sub_capability") or getattr(self.instance, "sub_capability", None)
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
