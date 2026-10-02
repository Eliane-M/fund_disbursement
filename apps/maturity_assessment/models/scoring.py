from django.conf import settings
from django.db import models

from apps.core.models.base import UUIDPrimaryKey


class MaturityBandQuerySet(models.QuerySet):
    def resolve(self, assessment_id, score):
        """
        Round the overall score first, then pick the containing band.
        Falls back to the nearest band so a result is never band-less.
        """
        rounded = round(float(score))
        bands = list(self.filter(assessment_id=assessment_id))
        if not bands:
            return None
        for band in bands:
            if band.min_score <= rounded <= band.max_score:
                return band
        return min(
            bands,
            key=lambda band: abs(rounded - float((band.min_score + band.max_score) / 2)),
        )


class MaturityBand(UUIDPrimaryKey):
    assessment = models.ForeignKey(
        "maturity_assessment.Assessment",
        on_delete=models.CASCADE,
        related_name="maturity_bands",
    )
    label = models.TextField()
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    color_hex = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)

    objects = MaturityBandQuerySet.as_manager()

    class Meta:
        db_table = "maturity_bands"
        constraints = [
            models.UniqueConstraint(fields=["assessment", "label"], name="maturity_bands_assessment_label_uniq"),
            models.CheckConstraint(condition=models.Q(min_score__gte=0), name="maturity_bands_min_gte_0"),
            models.CheckConstraint(condition=models.Q(max_score__lte=100), name="maturity_bands_max_lte_100"),
            models.CheckConstraint(
                condition=models.Q(max_score__gte=models.F("min_score")),
                name="maturity_bands_range",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.min_score}–{self.max_score})"


class Recommendation(UUIDPrimaryKey):
    assessment = models.ForeignKey(
        "maturity_assessment.Assessment",
        on_delete=models.CASCADE,
        related_name="recommendations",
    )
    capability = models.ForeignKey(
        "maturity_assessment.Capability",
        on_delete=models.CASCADE,
        related_name="recommendations",
    )
    band = models.ForeignKey(
        MaturityBand,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="recommendations",
    )
    recommendation_text = models.TextField()
    display_order = models.IntegerField(default=0)

    class Meta:
        db_table = "recommendations"
        constraints = [
            models.UniqueConstraint(
                fields=["capability", "band"],
                name="recommendations_capability_band_uniq",
                condition=models.Q(band__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["capability"],
                name="recommendations_capability_gap_uniq",
                condition=models.Q(band__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.capability} · {self.band_id or 'gap'}"


class AssessmentVersion(UUIDPrimaryKey):
    assessment = models.ForeignKey(
        "maturity_assessment.Assessment",
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_no = models.IntegerField()
    snapshot = models.JSONField()
    change_note = models.TextField(blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_assessment_versions",
    )
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assessment_versions"
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "version_no"],
                name="assessment_versions_assessment_no_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.assessment_id} v{self.version_no}"
