from flask import redirect, render_template, url_for
from flask_login import current_user

from app.decorators import role_chosen_required
from app.main import bp


@bp.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if not current_user.has_role:
        return redirect(url_for("auth.choose_role"))
    return redirect(url_for("main.home"))


@bp.route("/home")
@role_chosen_required
def home():
    # Placeholder landing page. The marketplace, settings, seller portal and
    # admin portal will replace or link from here in later stages.
    return render_template("main/home.html")
