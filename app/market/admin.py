from datetime import timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from app import db
from app.market import admin_bp as bp
from app.market.forms import NoteForm, ReportResolveForm, UserModerationForm
from app.market.models import (
    Listing,
    ListingStatus,
    ModAction,
    ModerationAction,
    ModerationNote,
    Report,
    ReportStatus,
    Review,
    ReviewStatus,
    active_ban,
    utcnow,
)
from app.market.permissions import role_required
from app.models import Role, User


def _moderatable_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.role == Role.ADMIN:
        abort(403)  # admins can't moderate other admins
    return user


def _apply_action(target, action, reason, ban_days=None, report=None):
    if action == ModAction.UNBAN and active_ban(target) is None:
        return None
    entry = ModerationAction(
        target_user_id=target.id,
        admin_id=current_user.id,
        report_id=report.id if report else None,
        action=action,
        reason=reason,
        expires_at=utcnow() + timedelta(days=ban_days) if action == ModAction.TEMP_BAN else None,
    )
    db.session.add(entry)
    return entry


def _remove_listing(listing, reason):
    listing.status = ListingStatus.REMOVED
    listing.removed_reason = reason


def _remove_review(review):
    review.status = ReviewStatus.REMOVED


# ---------- Reports inbox ----------

@bp.route("/")
@role_required(Role.ADMIN)
def index():
    status = request.args.get("status", ReportStatus.OPEN)
    query = Report.query
    if status in (ReportStatus.OPEN, ReportStatus.RESOLVED, ReportStatus.DISMISSED):
        query = query.filter_by(status=status)
    else:
        status = "all"
    reports = query.order_by(Report.created_at.desc()).all()
    open_count = Report.query.filter_by(status=ReportStatus.OPEN).count()
    return render_template("admin/index.html", reports=reports, status=status, open_count=open_count)


@bp.route("/reports/<int:report_id>", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def report_detail(report_id):
    report = db.get_or_404(Report, report_id)
    target = report.target_user
    form = ReportResolveForm()

    if form.validate_on_submit():
        if report.status != ReportStatus.OPEN:
            flash("This report is already closed.", "info")
            return redirect(url_for("admin.report_detail", report_id=report.id))
        if target.role == Role.ADMIN:
            abort(403)

        outcome = form.outcome.data
        if outcome in (ModAction.WARNING, ModAction.TEMP_BAN, ModAction.PERM_BAN):
            _apply_action(target, outcome, form.note.data, form.ban_days.data, report)

        if outcome == "content_only" or form.remove_content.data:
            if report.listing:
                _remove_listing(report.listing, form.note.data)
            if report.review:
                _remove_review(report.review)

        db.session.add(
            ModerationNote(target_user_id=target.id, admin_id=current_user.id, report_id=report.id, body=form.note.data)
        )
        report.status = ReportStatus.DISMISSED if outcome == "dismiss" else ReportStatus.RESOLVED
        report.resolved_by_id = current_user.id
        report.resolved_at = utcnow()
        db.session.commit()
        flash(f"Report #{report.id} closed.", "success")
        return redirect(url_for("admin.index"))

    other_reports = (
        Report.query.filter(Report.target_user_id == target.id, Report.id != report.id)
        .order_by(Report.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "admin/report.html",
        report=report,
        target=target,
        form=form,
        other_reports=other_reports,
        ban=active_ban(target),
    )


# ---------- User search and moderation ----------

@bp.route("/users")
@role_required(Role.ADMIN)
def users():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        term = f"%{q.lower()}%"
        results = (
            User.query.filter(or_(User.username_lower.like(term), User.display_name.ilike(term)))
            .order_by(User.username_lower)
            .limit(50)
            .all()
        )
    bans = {u.id: active_ban(u) for u in results}
    return render_template("admin/users.html", q=q, results=results, bans=bans)


@bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def user_detail(user_id):
    user = db.get_or_404(User, user_id)
    action_form = UserModerationForm(prefix="act")
    note_form = NoteForm(prefix="note")
    is_admin_target = user.role == Role.ADMIN

    if action_form.submit_action.data and action_form.validate_on_submit():
        if is_admin_target:
            abort(403)
        entry = _apply_action(user, action_form.action.data, action_form.reason.data, action_form.ban_days.data)
        if entry is None:
            flash(f"@{user.username} isn't banned.", "info")
        else:
            db.session.commit()
            flash(f"{entry.label} applied to @{user.username}.", "success")
        return redirect(url_for("admin.user_detail", user_id=user.id))

    if note_form.submit_note.data and note_form.validate_on_submit():
        db.session.add(ModerationNote(target_user_id=user.id, admin_id=current_user.id, body=note_form.body.data))
        db.session.commit()
        flash("Note added.", "success")
        return redirect(url_for("admin.user_detail", user_id=user.id))

    actions = (
        ModerationAction.query.filter_by(target_user_id=user.id)
        .order_by(ModerationAction.created_at.desc())
        .all()
    )
    notes = (
        ModerationNote.query.filter_by(target_user_id=user.id).order_by(ModerationNote.created_at.desc()).all()
    )
    reports = Report.query.filter_by(target_user_id=user.id).order_by(Report.created_at.desc()).all()
    listings = Listing.query.filter_by(seller_id=user.id).order_by(Listing.created_at.desc()).all()
    reviews = Review.query.filter_by(buyer_id=user.id).order_by(Review.created_at.desc()).all()
    return render_template(
        "admin/user.html",
        user=user,
        ban=active_ban(user),
        action_form=action_form,
        note_form=note_form,
        is_admin_target=is_admin_target,
        actions=actions,
        notes=notes,
        reports=reports,
        listings=listings,
        reviews=reviews,
    )


# ---------- Direct content removal ----------

@bp.route("/listings/<int:listing_id>/remove", methods=["POST"])
@role_required(Role.ADMIN)
def remove_listing(listing_id):
    listing = db.get_or_404(Listing, listing_id)
    reason = request.form.get("reason", "").strip() or "Removed by a moderator."
    _remove_listing(listing, reason[:1000])
    db.session.add(
        ModerationNote(
            target_user_id=listing.seller_id,
            admin_id=current_user.id,
            body=f"Removed listing #{listing.id} \u201c{listing.title}\u201d: {reason[:1000]}",
        )
    )
    db.session.commit()
    flash("Listing removed.", "success")
    return redirect(url_for("market.listing_detail", listing_id=listing.id))


@bp.route("/reviews/<int:review_id>/remove", methods=["POST"])
@role_required(Role.ADMIN)
def remove_review(review_id):
    review = db.get_or_404(Review, review_id)
    _remove_review(review)
    db.session.add(
        ModerationNote(
            target_user_id=review.buyer_id,
            admin_id=current_user.id,
            body=f"Removed review #{review.id} on @{review.seller.username}.",
        )
    )
    db.session.commit()
    flash("Review removed.", "success")
    return redirect(url_for("market.seller_profile", seller_id=review.seller_id))
