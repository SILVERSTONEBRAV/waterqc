from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to modify objects.
    All other users can only read objects.
    """

    def has_permission(self, request, view):
        # Read permissions are allowed to any user, so we'll always allow GET, HEAD, or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to admins.
        return request.user and request.user.is_staff


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    All other users can only read objects.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any user, so we'll always allow GET, HEAD, or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the object.
        return obj.created_by == request.user


class IsAnalystOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow only analysts or admins to update a HeavyMetalAnalysis object.
    """

    def has_permission(self, request, view):
        # Allow admin to perform any action
        if request.user and request.user.is_staff:
            return True

        # Only allow 'analyst' role to modify HeavyMetalAnalysis objects
        if view.action in ['update', 'partial_update']:
            return request.user.groups.filter(name='Analysts').exists()

        # If it's a read action (GET), allow all users
        return request.method in permissions.SAFE_METHODS


class CanTransitionState(permissions.BasePermission):
    """
    Custom permission to check if a user has permission to transition the state of an analysis.
    """

    def has_permission(self, request, view):
        # You can add your custom logic here to check if the user can transition states
        # For example, allow only the user who created the analysis or an admin
        analysis = view.get_object()
        if request.method == 'POST':  # Transitioning state via POST
            if analysis.created_by == request.user or request.user.is_staff:
                return True
        return False
