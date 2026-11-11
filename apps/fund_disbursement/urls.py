from django.urls import path

from apps.fund_disbursement import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="fd-dashboard"),
    path("review-queue/", views.review_queue, name="fd-review-queue"),
    path(
        "evidence-requirement-types/",
        views.EvidenceRequirementTypeListCreateView.as_view(),
        name="fd-evidence-requirement-types",
    ),
    path("my/funds/", views.my_funds, name="fd-my-funds"),
    path("my/funds/<uuid:pk>/", views.my_fund_detail, name="fd-my-fund-detail"),
    path("my/installments/<uuid:pk>/", views.my_installment_detail, name="fd-my-installment"),
    path("my/installments/<uuid:pk>/submit-evidence/", views.my_submit_evidence, name="fd-my-submit-evidence"),
    path("evidence-files/<uuid:pk>/download/", views.evidence_file_download, name="fd-evidence-download"),
    path("funds/", views.FundListCreateView.as_view(), name="fd-funds"),
    path("funds/<uuid:pk>/", views.FundDetailView.as_view(), name="fd-fund-detail"),
    path("funds/<uuid:pk>/lifecycle/", views.fund_lifecycle, name="fd-fund-lifecycle"),
    path(
        "funds/<uuid:fund_id>/milestones/",
        views.MilestoneListCreateView.as_view(),
        name="fd-fund-milestones",
    ),
    path("milestones/<uuid:pk>/", views.MilestoneDetailView.as_view(), name="fd-milestone-detail"),
    path(
        "milestones/<uuid:milestone_id>/kpis/",
        views.MilestoneKPIListCreateView.as_view(),
        name="fd-milestone-kpis",
    ),
    path("kpis/<uuid:pk>/", views.MilestoneKPIDetailView.as_view(), name="fd-kpi-detail"),
    path(
        "milestones/<uuid:milestone_id>/evidence-requirements/",
        views.MilestoneEvidenceRequirementListCreateView.as_view(),
        name="fd-milestone-evidence-requirements",
    ),
    path(
        "evidence-requirements/<uuid:pk>/",
        views.MilestoneEvidenceRequirementDetailView.as_view(),
        name="fd-evidence-requirement-detail",
    ),
    path("funds/<uuid:fund_id>/installments/", views.InstallmentListView.as_view(), name="fd-fund-installments"),
    path("installments/<uuid:pk>/", views.InstallmentDetailView.as_view(), name="fd-installment-detail"),
    path("installments/<uuid:pk>/submit-evidence/", views.submit_evidence, name="fd-submit-evidence"),
    path("installments/<uuid:pk>/disburse/", views.disburse_installment, name="fd-disburse"),
    path("submissions/<uuid:pk>/decide/", views.decide_submission, name="fd-decide-submission"),
]
