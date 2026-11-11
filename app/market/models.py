"""Tables for the marketplace, messaging, reviews, reports and moderation.

These live in their own tables and never add columns to the users table,
so db.create_all() can add them to an existing database without touching
existing accounts.
"""
from datetime import datetime, timezone

from app import db
from app.models import User


def utcnow():
    # Stored without tzinfo; every timestamp in these tables is UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


CATEGORIES = [
    ("electronics", "Electronics"),
    ("furniture", "Furniture"),
    ("clothing", "Clothing and shoes"),
    ("books", "Books"),
    ("home", "Home and kitchen"),
    ("sports", "Sports and outdoors"),
    ("toys", "Toys and games"),
    ("other", "Other"),
]
CATEGORY_LABELS = dict(CATEGORIES)


class ListingStatus:
    ACTIVE = "active"
    SOLD = "sold"
    REMOVED = "removed"  # removed by an admin; the seller can't bring it back


class Listing(db.Model):
    __tablename__ = "listings"

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    shipping_fee = db.Column(db.Numeric(10, 2), nullable=True)
    location = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(30), nullable=False, index=True)
    # Images are stored in the database because Cloud Run's disk is wiped on
    # every deploy, so files saved there would disappear.
    image_data = db.Column(db.LargeBinary, nullable=False)
    image_mimetype = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(10), nullable=False, default=ListingStatus.ACTIVE, index=True)
    removed_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    seller = db.relationship(User, foreign_keys=[seller_id])

    @property
    def category_label(self):
        return CATEGORY_LABELS.get(self.category, self.category)

    @property
    def total_price(self):
        return self.price + (self.shipping_fee or 0)


class Message(db.Model):
    """One message in a conversation. A conversation is a listing plus a buyer."""

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.id"), nullable=False, index=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    listing = db.relationship(Listing)
    buyer = db.relationship(User, foreign_keys=[buyer_id])
    sender = db.relationship(User, foreign_keys=[sender_id])


class ReviewStatus:
    ACTIVE = "active"
    REMOVED = "removed"


class Review(db.Model):
    __tablename__ = "reviews"
    __table_args__ = (db.UniqueConstraint("seller_id", "buyer_id", name="uq_review_once_per_seller"),)

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(10), nullable=False, default=ReviewStatus.ACTIVE)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    seller = db.relationship(User, foreign_keys=[seller_id])
    buyer = db.relationship(User, foreign_keys=[buyer_id])


REPORT_REASONS = [
    ("scam", "Scam or fraud"),
    ("harassment", "Harassment or abusive messages"),
    ("prohibited", "Prohibited or counterfeit item"),
    ("misleading", "Misleading listing"),
    ("fake_review", "Fake or bad-faith review"),
    ("other", "Something else"),
]
REPORT_REASON_LABELS = dict(REPORT_REASONS)


class ReportStatus:
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.id"), nullable=True)
    review_id = db.Column(db.Integer, db.ForeignKey("reviews.id"), nullable=True)
    reason = db.Column(db.String(20), nullable=False)
    details = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(10), nullable=False, default=ReportStatus.OPEN, index=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    reporter = db.relationship(User, foreign_keys=[reporter_id])
    target_user = db.relationship(User, foreign_keys=[target_user_id])
    resolved_by = db.relationship(User, foreign_keys=[resolved_by_id])
    listing = db.relationship(Listing)
    review = db.relationship(Review)

    @property
    def reason_label(self):
        return REPORT_REASON_LABELS.get(self.reason, self.reason)


class ModAction:
    WARNING = "warning"
    TEMP_BAN = "temp_ban"
    PERM_BAN = "perm_ban"
    UNBAN = "unban"

    LABELS = {
        WARNING: "Warning",
        TEMP_BAN: "Temporary ban",
        PERM_BAN: "Permanent ban",
        UNBAN: "Ban lifted",
    }
    BAN_STATE_ACTIONS = (TEMP_BAN, PERM_BAN, UNBAN)


class ModerationAction(db.Model):
    """Warnings and bans. The newest ban or unban decides whether a user is banned."""

    __tablename__ = "moderation_actions"

    id = db.Column(db.Integer, primary_key=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=True)
    action = db.Column(db.String(10), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)  # only for temporary bans
    acknowledged_at = db.Column(db.DateTime, nullable=True)  # when the user dismissed a warning
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    target_user = db.relationship(User, foreign_keys=[target_user_id])
    admin = db.relationship(User, foreign_keys=[admin_id])

    @property
    def label(self):
        return ModAction.LABELS.get(self.action, self.action)


class ModerationNote(db.Model):
    """Private notes admins leave on a user. Never shown to the user."""

    __tablename__ = "moderation_notes"

    id = db.Column(db.Integer, primary_key=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    admin = db.relationship(User, foreign_keys=[admin_id])


def active_ban(user):
    """Return the ban currently in force for a user, or None."""
    latest = (
        ModerationAction.query.filter(
            ModerationAction.target_user_id == user.id,
            ModerationAction.action.in_(ModAction.BAN_STATE_ACTIONS),
        )
        .order_by(ModerationAction.created_at.desc(), ModerationAction.id.desc())
        .first()
    )
    if latest is None or latest.action == ModAction.UNBAN:
        return None
    if latest.action == ModAction.TEMP_BAN and latest.expires_at <= utcnow():
        return None
    return latest
