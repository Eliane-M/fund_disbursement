from django.contrib import admin

from apps.core.models import (
    AuditLog,
    DashboardLink,
    DashboardLinkGroup,
    DashboardLinkVisit,
    EmailTemplate,
    File,
    Notification,
    Organization,
    OrganizationModule,
    OrganizationSetting,
    OrganizationSubscription,
    Plan,
    Respondent,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("tenant_no", "name", "slug", "status", "default_currency")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(OrganizationModule)
class OrganizationModuleAdmin(admin.ModelAdmin):
    list_display = ("organization", "module", "is_enabled", "enabled_at")
    list_filter = ("module", "is_enabled")


@admin.register(OrganizationSetting)
class OrganizationSettingAdmin(admin.ModelAdmin):
    list_display = ("organization", "module", "updated_at")
    list_filter = ("module",)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price_per_month", "currency", "is_active")
    list_filter = ("is_active",)


@admin.register(OrganizationSubscription)
class OrganizationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "started_at")
    list_filter = ("status",)


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "organization", "purpose", "scan_status", "created_at")
    list_filter = ("purpose", "scan_status")
    search_fields = ("original_filename", "storage_key")


@admin.register(Respondent)
class RespondentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "respondent_type", "status")
    list_filter = ("respondent_type", "status")
    search_fields = ("name", "legal_name", "registration_no")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "entity_type", "organization", "actor_user", "created_at")
    list_filter = ("action", "entity_type")
    search_fields = ("summary", "action")
    readonly_fields = [field.name for field in AuditLog._meta.fields]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("template_key", "channel", "status", "organization", "scheduled_for")
    list_filter = ("channel", "status")


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("template_key", "locale", "organization", "is_active")
    list_filter = ("locale", "is_active")


@admin.register(DashboardLinkGroup)
class DashboardLinkGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "display_order")


@admin.register(DashboardLink)
class DashboardLinkAdmin(admin.ModelAdmin):
    list_display = ("title", "group", "organization", "link_kind")
    list_filter = ("link_kind",)


@admin.register(DashboardLinkVisit)
class DashboardLinkVisitAdmin(admin.ModelAdmin):
    list_display = ("link", "user", "opened_at")
