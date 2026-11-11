from functools import wraps

from flask import abort
from flask_login import current_user

from app.decorators import role_chosen_required


def role_required(*roles):
    """Allow only users whose role is in roles. Everyone else gets a 403.

    Builds on role_chosen_required, so it also requires login and a chosen role.
    """

    def decorator(view):
        @wraps(view)
        @role_chosen_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
