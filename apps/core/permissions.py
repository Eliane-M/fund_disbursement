from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import MembershipStatus, OrganizationMembership


def get_active_membership(user, organization_id):
    return (
        OrganizationMembership.objects.filter(
            user=user,
            organization_id=organization_id,
            status=MembershipStatus.ACTIVE,
        )
        .select_related("organization")
        .first()
    )


def assert_org_member(user, organization_id, roles=None):
    """Raise PermissionDenied unless the user has an active membership in the org.

    When `roles` is given, the membership's role must be one of them.
    """
    membership = get_active_membership(user, organization_id)
    if membership is None:
        raise PermissionDenied("You are not a member of this organization.")
    if roles is not None and membership.role not in roles:
        raise PermissionDenied("You do not have permission to perform this action.")
    return membership


def require_organization_id(request):
    org_id = request.query_params.get("organization") or request.data.get("organization")
    if not org_id:
        raise ValidationError({"organization": "This query parameter is required."})
    return org_id
