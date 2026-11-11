from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app import db
from app.market import seller_bp as bp
from app.market.forms import ListingForm
from app.market.models import Listing, ListingStatus, Message, Report
from app.market.permissions import role_required
from app.models import Role

# Check the file's first bytes, not just its name, so a renamed file can't pass as a photo.
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}


def _read_image(file_storage):
    data = file_storage.read()
    for signature, mimetype in IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            return data, mimetype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data, "image/webp"
    return None, None


def _own_listing(listing_id):
    listing = db.get_or_404(Listing, listing_id)
    if listing.seller_id != current_user.id:
        abort(404)  # don't reveal other sellers' listings exist
    return listing


def _fill_listing(listing, form):
    listing.title = form.title.data
    listing.description = form.description.data
    listing.category = form.category.data
    listing.price = form.price.data
    listing.shipping_fee = form.shipping_fee.data
    listing.location = form.location.data


@bp.route("/")
@role_required(Role.SELLER)
def index():
    listings = Listing.query.filter_by(seller_id=current_user.id).order_by(Listing.created_at.desc()).all()
    return render_template("seller/index.html", listings=listings)


@bp.route("/listings/new", methods=["GET", "POST"])
@role_required(Role.SELLER)
def new_listing():
    form = ListingForm(require_photo=True)
    if form.validate_on_submit():
        data, mimetype = _read_image(form.photo.data)
        if data is None:
            form.photo.errors.append("That file isn't a valid JPG, PNG, or WebP image.")
        else:
            listing = Listing(seller_id=current_user.id, image_data=data, image_mimetype=mimetype)
            _fill_listing(listing, form)
            db.session.add(listing)
            db.session.commit()
            flash("Listing published.", "success")
            return redirect(url_for("market.listing_detail", listing_id=listing.id))
    return render_template("seller/listing_form.html", form=form, listing=None)


@bp.route("/listings/<int:listing_id>/edit", methods=["GET", "POST"])
@role_required(Role.SELLER)
def edit_listing(listing_id):
    listing = _own_listing(listing_id)
    if listing.status == ListingStatus.REMOVED:
        flash("A moderator removed this listing, so it can't be edited.", "error")
        return redirect(url_for("seller.index"))

    form = ListingForm(obj=listing, require_photo=False)
    if form.validate_on_submit():
        if form.photo.data:
            data, mimetype = _read_image(form.photo.data)
            if data is None:
                form.photo.errors.append("That file isn't a valid JPG, PNG, or WebP image.")
                return render_template("seller/listing_form.html", form=form, listing=listing)
            listing.image_data, listing.image_mimetype = data, mimetype
        _fill_listing(listing, form)
        db.session.commit()
        flash("Listing saved.", "success")
        return redirect(url_for("market.listing_detail", listing_id=listing.id))
    return render_template("seller/listing_form.html", form=form, listing=listing)


@bp.route("/listings/<int:listing_id>/status", methods=["POST"])
@role_required(Role.SELLER)
def toggle_sold(listing_id):
    listing = _own_listing(listing_id)
    if listing.status == ListingStatus.REMOVED:
        abort(403)
    listing.status = ListingStatus.ACTIVE if listing.status == ListingStatus.SOLD else ListingStatus.SOLD
    db.session.commit()
    flash("Marked as sold." if listing.status == ListingStatus.SOLD else "Listing is active again.", "success")
    return redirect(url_for("seller.index"))


@bp.route("/listings/<int:listing_id>/delete", methods=["POST"])
@role_required(Role.SELLER)
def delete_listing(listing_id):
    listing = _own_listing(listing_id)
    # Keep listings that have messages or reports so the history stays intact for moderators.
    has_history = (
        Message.query.filter_by(listing_id=listing.id).first() is not None
        or Report.query.filter_by(listing_id=listing.id).first() is not None
    )
    if has_history or listing.status == ListingStatus.REMOVED:
        flash("This listing has messages or reports attached, so it can't be deleted. Mark it as sold instead.", "error")
        return redirect(url_for("seller.index"))
    db.session.delete(listing)
    db.session.commit()
    flash("Listing deleted.", "success")
    return redirect(url_for("seller.index"))
