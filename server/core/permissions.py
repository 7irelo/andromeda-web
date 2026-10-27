"""
Object-level permissions shared by every app.

Reads are filtered by ``core.visibility`` in ``get_queryset()``; these classes
gate writes so a user can only modify what they own or administer.
"""
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated

# Custom actions (react, join, follow, ...) enforce their own rules; these
# classes guard editing and deleting the object itself.
MUTATING_ACTIONS = {'update', 'partial_update', 'destroy'}


class _AuthenticatedBase(IsAuthenticated):
    """
    Setting ``permission_classes`` on a view replaces the global default, so
    every class here must keep requiring authentication itself.
    """


def _is_read_or_action(request, view):
    return request.method in SAFE_METHODS or getattr(view, 'action', None) not in MUTATING_ACTIONS


class IsOwnerOrReadOnly(_AuthenticatedBase):
    """Allow writes only to the user referenced by ``view.owner_field``."""

    message = 'You can only modify your own content.'

    def has_object_permission(self, request, view, obj):
        if _is_read_or_action(request, view):
            return True
        owner_field = getattr(view, 'owner_field', 'author')
        return getattr(obj, f'{owner_field}_id', None) == request.user.id


class IsGroupAdminOrReadOnly(_AuthenticatedBase):
    message = 'Only group admins can do that.'

    def has_object_permission(self, request, view, obj):
        if _is_read_or_action(request, view):
            return True
        return obj.memberships.filter(user=request.user, role='admin').exists()


class IsPageAdminOrReadOnly(_AuthenticatedBase):
    message = 'Only page admins can do that.'

    def has_object_permission(self, request, view, obj):
        if _is_read_or_action(request, view):
            return True
        return is_page_admin(request.user, obj)


def is_page_admin(user, page, roles=('admin',)):
    return page.created_by_id == user.id or page.admins.filter(user=user, role__in=roles).exists()
