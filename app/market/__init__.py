"""Settings, marketplace, seller portal, messaging, reviews, reports and admin portal."""
import os

import click
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, logout_user

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")
market_bp = Blueprint("market", __name__)
seller_bp = Blueprint("seller", __name__, url_prefix="/seller")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from app.market import admin, marketplace, seller, settings  # noqa: E402,F401
from app.market.models import ModAction, ModerationAction, active_ban  # noqa: E402

# Pages a banned user is still allowed to load on their way out.
BAN_EXEMPT_ENDPOINTS = {"static", "auth.login", "auth.signup", "auth.logout"}


def register_market(app):
    """Called once from create_app to plug these pages into the app."""
    # Listing photos are capped at 2 MB; this rejects anything far larger before it's read.
    app.config.setdefault("MAX_CONTENT_LENGTH", 3 * 1024 * 1024)

    for bp in (settings_bp, market_bp, seller_bp, admin_bp):
        app.register_blueprint(bp)

    @app.before_request
    def block_banned_users():
        if not current_user.is_authenticated or request.endpoint in BAN_EXEMPT_ENDPOINTS:
            return None
        ban = active_ban(current_user)
        if ban is None:
            return None
        logout_user()
        if ban.action == ModAction.PERM_BAN:
            flash(f"Your account has been permanently banned. Reason: {ban.reason}", "error")
        else:
            until = ban.expires_at.strftime("%b %d, %Y at %H:%M UTC")
            flash(f"Your account is banned until {until}. Reason: {ban.reason}", "error")
        return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_unseen_warnings():
        if not current_user.is_authenticated or not current_user.has_role:
            return {"unseen_warnings": []}
        warnings = ModerationAction.query.filter_by(
            target_user_id=current_user.id, action=ModAction.WARNING, acknowledged_at=None
        ).all()
        return {"unseen_warnings": warnings}

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("errors/error.html", code=403, message="You don't have access to that page."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("errors/error.html", code=404, message="That page doesn't exist."), 404

    @app.errorhandler(413)
    def too_large(_):
        return render_template("errors/error.html", code=413, message="That file is too large. Photos must be 2 MB or smaller."), 413

    @app.cli.command("create-admin")
    @click.option("--username", default=lambda: os.environ.get("ADMIN_USERNAME"), help="Admin username, no spaces.")
    @click.option("--display-name", default=lambda: os.environ.get("ADMIN_DISPLAY_NAME", "Admin"))
    def create_admin(username, display_name):
        """Create an administrator. Admins can't sign up through the website."""
        from app import db
        from app.models import Role, User

        if not username or any(c.isspace() for c in username) or not 3 <= len(username) <= 30:
            raise click.ClickException("Give a 3 to 30 character username with no spaces via --username or ADMIN_USERNAME.")
        if User.find_by_username(username):
            raise click.ClickException(f"User '{username}' already exists.")
        password = os.environ.get("ADMIN_PASSWORD") or click.prompt(
            "Admin password", hide_input=True, confirmation_prompt=True
        )
        if len(password) < 8:
            raise click.ClickException("Admin password must be at least 8 characters.")
        admin_user = User(username=username, display_name=display_name, password=password)
        admin_user.role = Role.ADMIN
        db.session.add(admin_user)
        db.session.commit()
        click.echo(f"Created admin '{username}'.")
