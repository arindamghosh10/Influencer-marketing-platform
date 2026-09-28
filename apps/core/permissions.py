from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Allow the view only for users whose role is in `roles`."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            user = request.user
            if user.role not in roles and not ("ops" in roles and user.is_ops):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


brand_required = role_required("brand")
creator_required = role_required("creator")
ops_required = role_required("ops")
