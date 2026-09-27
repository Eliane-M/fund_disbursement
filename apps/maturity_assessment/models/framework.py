from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import CreatedAtModel, TimestampedModel, UUIDPrimaryKey


class QuestionType(models.TextChoices):
    SINGLE_SELECT = "single_select", "Single select"
    MULTI_SELECT = "multi_select", "Multi select"
    LIKERT_5 = "likert_5", "Likert 5"
    NUMERIC = "numeric", "Numeric"
    YES_NO = "yes_no", "Yes / No"
    FREE_TEXT = "free_text", "Free text"


class Capability(CreatedAtModel):
    assessment = models.ForeignKey(
        "maturity_assessment.Assessment",
        on_delete=models.CASCADE,
        related_name="capabilities",
    )
    name = models.TextField()
    description = models.TextField(blank=True)
    weight_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    target_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    display_order = models.IntegerField(default=0)
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "capabilities"
        constraints = [
            models.UniqueConstraint(fields=["id", "assessment"], name="capabilities_id_assessment_uniq"),
            models.CheckConstraint(
                condition=models.Q(weight_pct__gte=0, weight_pct__lte=100),
                name="capabilities_weight_range",
            ),
        ]
        indexes = [
            models.Index(fields=["assessment", "display_order"], name="ix_capabilities_assessment"),
        ]

    def __str__(self):
        return self.name


class SubCapability(CreatedAtModel):
    capability = models.ForeignKey(
        Capability,
        on_delete=models.CASCADE,
        related_name="sub_capabilities",
    )
    name = models.TextField()
    description = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "sub_capabilities"
        constraints = [
            models.UniqueConstraint(
                fields=["id", "capability"],
                name="sub_capabilities_id_capability_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["capability", "display_order"], name="ix_subcapabilities_capability"),
        ]

    def __str__(self):
        return self.name


class Question(TimestampedModel):
    assessment = models.ForeignKey(
        "maturity_assessment.Assessment",
        on_delete=models.CASCADE,
        related_name="questions",
    )
    capability = models.ForeignKey(
        Capability,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    sub_capability = models.ForeignKey(
        SubCapability,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )
    question_text = models.TextField()
    help_text = models.TextField(blank=True)
    question_type = models.CharField(max_length=16, choices=QuestionType.choices)
    is_required = models.BooleanField(default=True)
    is_scored = models.BooleanField(default=True)
    allow_not_applicable = models.BooleanField(default=False)
    max_points = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    numeric_unit = models.TextField(blank=True)
    numeric_min = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    numeric_max = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    display_order = models.IntegerField(default=0)
    page_no = models.IntegerField(default=1)
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "questions"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(question_type__in=QuestionType.values),
                name="questions_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(max_points__gt=0),
                name="questions_max_points_positive",
            ),
            models.CheckConstraint(
                condition=~models.Q(question_type=QuestionType.FREE_TEXT) | models.Q(is_scored=False),
                name="questions_free_text_not_scored",
            ),
        ]
        indexes = [
            models.Index(
                fields=["assessment", "page_no", "display_order"],
                name="ix_questions_assessment",
                condition=models.Q(is_archived=False),
            ),
            models.Index(fields=["capability"], name="ix_questions_capability"),
        ]

    def clean(self):
        if self.capability_id and self.capability.assessment_id != self.assessment_id:
            raise ValidationError("Capability must belong to the same assessment.")
        if self.sub_capability_id and self.sub_capability.capability_id != self.capability_id:
            raise ValidationError("Sub-capability must belong to the stated capability.")

    def __str__(self):
        return self.question_text[:80]


class QuestionOption(UUIDPrimaryKey):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    label = models.TextField()
    score_value = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    likert_position = models.SmallIntegerField(null=True, blank=True)
    display_order = models.IntegerField(default=0)
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "question_options"
        constraints = [
            models.UniqueConstraint(fields=["id", "question"], name="question_options_id_question_uniq"),
            models.CheckConstraint(
                condition=models.Q(likert_position__isnull=True)
                | models.Q(likert_position__gte=1, likert_position__lte=5),
                name="question_options_likert_range",
            ),
        ]
        indexes = [
            models.Index(fields=["question", "display_order"], name="ix_question_options_question"),
        ]

    def __str__(self):
        return self.label


class QuestionNumericRule(UUIDPrimaryKey):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="numeric_rules")
    min_value = models.DecimalField(max_digits=14, decimal_places=2)
    max_value = models.DecimalField(max_digits=14, decimal_places=2)
    score_value = models.DecimalField(max_digits=6, decimal_places=2)
    display_order = models.IntegerField(default=0)

    class Meta:
        db_table = "question_numeric_rules"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_value__gte=models.F("min_value")),
                name="question_numeric_rules_range",
            ),
        ]
        indexes = [models.Index(fields=["question"], name="ix_numeric_rules_question")]

    def __str__(self):
        return f"{self.min_value}–{self.max_value} = {self.score_value}"
