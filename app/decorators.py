from functools import wraps

from flask import redirect, url_for
from flask_login import current_user, login_required


def role_chosen_required(view):
    """Require a logged-in user who has already picked buyer or seller.

    Use this on every page except login, sign up, logout and the role picker,
    so a user who closed the site before choosing is always sent back to choose.
    """

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.has_role:
            return redirect(url_for("auth.choose_role"))
        return view(*args, **kwargs)

    return wrapped
