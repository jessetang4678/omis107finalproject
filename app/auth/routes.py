from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.auth import bp
from app.auth.forms import LoginForm, SignupForm
from app.models import Role, User


def _safe_next(target):
    """Only allow redirects back to a path on this site."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return None
    return target


def _redirect_after_login():
    if not current_user.has_role:
        return redirect(url_for("auth.choose_role"))
    return redirect(url_for("main.home"))


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return _redirect_after_login()

    form = SignupForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            display_name=form.display_name.data,
            password=form.password.data,
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("auth.choose_role"))

    return render_template("auth/signup.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_after_login()

    form = LoginForm()
    if form.validate_on_submit():
        user = User.find_by_username(form.username.data)
        if user is None or not user.check_password(form.password.data):
            flash("Incorrect username or password.", "error")
        else:
            login_user(user)
            if not user.has_role:
                return redirect(url_for("auth.choose_role"))
            return redirect(_safe_next(request.args.get("next")) or url_for("main.home"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/choose-role", methods=["GET", "POST"])
@login_required
def choose_role():
    # The choice is made once; afterwards this page just sends you on.
    if current_user.has_role:
        return redirect(url_for("main.home"))

    error = None
    if request.method == "POST":
        role = request.form.get("role")
        if role in Role.SELECTABLE:
            current_user.role = role
            db.session.commit()
            flash(f"Welcome! You're all set up as a {role}.", "success")
            return redirect(url_for("main.home"))
        error = "Please choose Buyer or Seller to continue."

    return render_template("auth/choose_role.html", error=error)
