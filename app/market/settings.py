from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.decorators import role_chosen_required
from app.market import settings_bp as bp
from app.market.forms import DisplayNameForm, PasswordChangeForm
from app.market.models import ModAction, ModerationAction, utcnow


@bp.route("/", methods=["GET", "POST"])
@role_chosen_required
def index():
    name_form = DisplayNameForm(prefix="name")
    password_form = PasswordChangeForm(prefix="pw")

    # Two forms on one page; the submit button's name tells us which was sent.
    if name_form.submit_name.data and name_form.validate_on_submit():
        current_user.display_name = name_form.display_name.data
        db.session.commit()
        flash("Display name saved.", "success")
        return redirect(url_for("settings.index"))

    if password_form.submit_password.data and password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            password_form.current_password.errors.append("Current password is incorrect.")
        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(url_for("settings.index"))

    if request.method == "GET":
        name_form.display_name.data = current_user.display_name

    warnings = (
        ModerationAction.query.filter_by(target_user_id=current_user.id, action=ModAction.WARNING)
        .order_by(ModerationAction.created_at.desc())
        .all()
    )
    return render_template(
        "settings/index.html", name_form=name_form, password_form=password_form, warnings=warnings
    )


@bp.route("/warnings/<int:warning_id>/acknowledge", methods=["POST"])
@role_chosen_required
def acknowledge_warning(warning_id):
    warning = db.get_or_404(ModerationAction, warning_id)
    if warning.target_user_id != current_user.id or warning.action != ModAction.WARNING:
        abort(404)
    warning.acknowledged_at = warning.acknowledged_at or utcnow()
    db.session.commit()
    return redirect(request.referrer if request.referrer and request.referrer.startswith(request.host_url) else url_for("main.home"))
