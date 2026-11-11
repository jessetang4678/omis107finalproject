from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from app import db
from app.decorators import role_chosen_required
from app.market import market_bp as bp
from app.market.forms import MarketFilterForm, MessageForm, ReportForm, ReviewForm
from app.market.models import (
    Listing,
    ListingStatus,
    Message,
    Report,
    ReportStatus,
    Review,
    ReviewStatus,
)
from app.market.permissions import role_required
from app.models import Role, User

PER_PAGE = 12


def _can_see_listing(listing):
    """Removed listings are visible only to their seller and to admins."""
    if listing.status != ListingStatus.REMOVED:
        return True
    return current_user.role == Role.ADMIN or listing.seller_id == current_user.id


def _get_visible_listing(listing_id):
    listing = db.get_or_404(Listing, listing_id)
    if not _can_see_listing(listing):
        abort(404)
    return listing


# ---------- Marketplace ----------

@bp.route("/marketplace")
@role_chosen_required
def index():
    form = MarketFilterForm(request.args)
    query = Listing.query.filter(Listing.status == ListingStatus.ACTIVE)

    if form.validate():
        if form.q.data:
            term = f"%{form.q.data}%"
            query = query.filter(or_(Listing.title.ilike(term), Listing.description.ilike(term)))
        if form.category.data:
            query = query.filter(Listing.category == form.category.data)
        if form.min_price.data is not None:
            query = query.filter(Listing.price >= form.min_price.data)
        if form.max_price.data is not None:
            query = query.filter(Listing.price <= form.max_price.data)
        if form.location.data:
            query = query.filter(Listing.location.ilike(f"%{form.location.data}%"))
        if form.no_shipping_fee.data:
            query = query.filter(or_(Listing.shipping_fee.is_(None), Listing.shipping_fee == 0))

    order = {
        "price_asc": Listing.price.asc(),
        "price_desc": Listing.price.desc(),
    }.get(form.sort.data, Listing.created_at.desc())
    page = query.order_by(order, Listing.id.desc()).paginate(per_page=PER_PAGE, error_out=False)

    # Keep the current filters when moving between pages.
    filter_args = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("market/index.html", form=form, page=page, filter_args=filter_args)


@bp.route("/listings/<int:listing_id>")
@role_chosen_required
def listing_detail(listing_id):
    listing = _get_visible_listing(listing_id)
    return render_template("market/listing.html", listing=listing, seller_rating=_seller_rating(listing.seller_id))


@bp.route("/listings/<int:listing_id>/image")
@role_chosen_required
def listing_image(listing_id):
    listing = _get_visible_listing(listing_id)
    resp = Response(listing.image_data, mimetype=listing.image_mimetype)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# ---------- Seller profiles and reviews ----------

def _seller_rating(seller_id):
    avg, count = (
        db.session.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.seller_id == seller_id, Review.status == ReviewStatus.ACTIVE)
        .one()
    )
    return {"average": round(float(avg), 1) if avg else None, "count": count}


def _buyer_has_contacted(buyer_id, seller_id):
    """A buyer can review a seller only after messaging them about a listing."""
    return (
        db.session.query(Message.id)
        .join(Listing, Message.listing_id == Listing.id)
        .filter(Message.sender_id == buyer_id, Message.buyer_id == buyer_id, Listing.seller_id == seller_id)
        .first()
        is not None
    )


def _get_seller(seller_id):
    seller = db.get_or_404(User, seller_id)
    if seller.role != Role.SELLER:
        abort(404)
    return seller


@bp.route("/sellers/<int:seller_id>")
@role_chosen_required
def seller_profile(seller_id):
    seller = _get_seller(seller_id)
    listings = (
        Listing.query.filter_by(seller_id=seller.id, status=ListingStatus.ACTIVE)
        .order_by(Listing.created_at.desc())
        .all()
    )
    reviews_q = Review.query.filter_by(seller_id=seller.id)
    if current_user.role != Role.ADMIN:
        reviews_q = reviews_q.filter_by(status=ReviewStatus.ACTIVE)
    reviews = reviews_q.order_by(Review.created_at.desc()).all()

    review_form = None
    review_blocked_reason = None
    my_review = None
    if current_user.role == Role.BUYER:
        my_review = Review.query.filter_by(seller_id=seller.id, buyer_id=current_user.id).first()
        if my_review and my_review.status == ReviewStatus.REMOVED:
            review_blocked_reason = "A moderator removed your review of this seller."
        elif not _buyer_has_contacted(current_user.id, seller.id):
            review_blocked_reason = "Message this seller about one of their listings before leaving a review."
        else:
            review_form = ReviewForm(obj=my_review) if my_review else ReviewForm()

    return render_template(
        "market/seller.html",
        seller=seller,
        listings=listings,
        reviews=reviews,
        rating=_seller_rating(seller.id),
        review_form=review_form,
        review_blocked_reason=review_blocked_reason,
        my_review=my_review,
    )


@bp.route("/sellers/<int:seller_id>/review", methods=["POST"])
@role_required(Role.BUYER)
def save_review(seller_id):
    seller = _get_seller(seller_id)
    form = ReviewForm()
    if not form.validate_on_submit():
        flash("Pick a rating and write a review.", "error")
        return redirect(url_for("market.seller_profile", seller_id=seller.id))

    if not _buyer_has_contacted(current_user.id, seller.id):
        abort(403)

    review = Review.query.filter_by(seller_id=seller.id, buyer_id=current_user.id).first()
    if review and review.status == ReviewStatus.REMOVED:
        abort(403)
    if review is None:
        review = Review(seller_id=seller.id, buyer_id=current_user.id)
        db.session.add(review)
        message = "Review posted."
    else:
        message = "Review updated."
    review.rating = form.rating.data
    review.body = form.body.data
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("market.seller_profile", seller_id=seller.id))


# ---------- Messages ----------

def _conversation_access(listing, buyer):
    """Only the buyer and the listing's seller can use a conversation. Admins can read it."""
    if current_user.id == buyer.id and current_user.role == Role.BUYER:
        return "participant"
    if current_user.id == listing.seller_id:
        return "participant"
    if current_user.role == Role.ADMIN:
        return "read_only"
    return None


@bp.route("/messages")
@role_required(Role.BUYER, Role.SELLER)
def inbox():
    if current_user.role == Role.BUYER:
        messages_q = Message.query.filter(Message.buyer_id == current_user.id)
    else:
        messages_q = Message.query.join(Listing, Message.listing_id == Listing.id).filter(
            Listing.seller_id == current_user.id
        )
    # Newest message first, then keep one entry per conversation.
    conversations = {}
    for msg in messages_q.order_by(Message.created_at.desc(), Message.id.desc()).all():
        conversations.setdefault((msg.listing_id, msg.buyer_id), msg)
    return render_template("market/inbox.html", conversations=list(conversations.values()))


@bp.route("/messages/<int:listing_id>/<int:buyer_id>", methods=["GET", "POST"])
@role_chosen_required
def conversation(listing_id, buyer_id):
    listing = db.get_or_404(Listing, listing_id)
    buyer = db.get_or_404(User, buyer_id)
    access = _conversation_access(listing, buyer)
    if access is None or buyer.role != Role.BUYER:
        abort(404)

    messages = (
        Message.query.filter_by(listing_id=listing.id, buyer_id=buyer.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    # Buyers can start a conversation only on an active listing.
    # Sellers can only reply to a conversation a buyer already started.
    can_send = access == "participant" and (
        (current_user.id == buyer.id and listing.status == ListingStatus.ACTIVE)
        or (current_user.id == listing.seller_id and messages)
    )
    form = MessageForm()
    if request.method == "POST":
        if not can_send:
            abort(403)
        if form.validate_on_submit():
            db.session.add(Message(listing_id=listing.id, buyer_id=buyer.id, sender_id=current_user.id, body=form.body.data))
            db.session.commit()
            return redirect(url_for("market.conversation", listing_id=listing.id, buyer_id=buyer.id))

    other_user = listing.seller if current_user.id == buyer.id else buyer
    return render_template(
        "market/conversation.html",
        listing=listing,
        buyer=buyer,
        other_user=other_user,
        messages=messages,
        form=form,
        can_send=can_send,
        read_only=access == "read_only",
    )


# ---------- Reports ----------

@bp.route("/report", methods=["GET", "POST"])
@role_required(Role.BUYER, Role.SELLER)
def report():
    """Report a user, optionally about one of their listings or reviews.

    Query string: user=<id>, plus optional listing=<id> or review=<id>.
    """
    target = db.get_or_404(User, request.args.get("user", type=int))
    if target.id == current_user.id or target.role == Role.ADMIN:
        abort(404)

    listing = review = None
    if request.args.get("listing"):
        listing = db.get_or_404(Listing, request.args.get("listing", type=int))
        if listing.seller_id != target.id or not _can_see_listing(listing):
            abort(404)
    if request.args.get("review"):
        review = db.get_or_404(Review, request.args.get("review", type=int))
        if review.buyer_id != target.id or review.status != ReviewStatus.ACTIVE:
            abort(404)

    form = ReportForm()
    if form.validate_on_submit():
        duplicate = Report.query.filter_by(
            reporter_id=current_user.id,
            target_user_id=target.id,
            listing_id=listing.id if listing else None,
            review_id=review.id if review else None,
            status=ReportStatus.OPEN,
        ).first()
        if duplicate:
            flash("You already reported this. A moderator will review it.", "info")
        else:
            db.session.add(
                Report(
                    reporter_id=current_user.id,
                    target_user_id=target.id,
                    listing_id=listing.id if listing else None,
                    review_id=review.id if review else None,
                    reason=form.reason.data,
                    details=form.details.data,
                )
            )
            db.session.commit()
            flash("Report sent. A moderator will review it.", "success")
        return redirect(url_for("market.index"))

    return render_template("market/report.html", form=form, target=target, listing=listing, review=review)
