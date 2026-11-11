import io

import pytest

from app import create_app, db
from app.market.models import (
    Listing,
    ListingStatus,
    Message,
    ModAction,
    ModerationAction,
    ModerationNote,
    Report,
    ReportStatus,
    Review,
    ReviewStatus,
    utcnow,
)
from app.models import Role, User
from config import TestConfig

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def app():
    app = create_app(TestConfig)
    yield app
    with app.app_context():
        db.drop_all()


def make_user(app, username, role):
    with app.app_context():
        user = User(username=username, display_name=username.title(), password="password123")
        user.role = role
        db.session.add(user)
        db.session.commit()
        return user.id


def client_for(app, username):
    c = app.test_client()
    c.post("/login", data={"username": username, "password": "password123"})
    return c


def listing_data(**overrides):
    data = {
        "title": "Desk lamp",
        "description": "Works great.",
        "category": "home",
        "price": "25.00",
        "shipping_fee": "",
        "location": "San Jose, CA",
        "photo": (io.BytesIO(PNG), "lamp.png"),
    }
    data.update(overrides)
    return data


def create_listing(c, **overrides):
    return c.post("/seller/listings/new", data=listing_data(**overrides), content_type="multipart/form-data")


@pytest.fixture
def users(app):
    ids = {
        "buyer": make_user(app, "bob", Role.BUYER),
        "buyer2": make_user(app, "bea", Role.BUYER),
        "seller": make_user(app, "sam", Role.SELLER),
        "seller2": make_user(app, "sue", Role.SELLER),
        "admin": make_user(app, "ada", Role.ADMIN),
    }
    return ids


@pytest.fixture
def listing_id(app, users):
    resp = create_listing(client_for(app, "sam"))
    assert resp.status_code == 302
    with app.app_context():
        return Listing.query.one().id


# ---------- Page access ----------

@pytest.mark.parametrize("path", ["/marketplace", "/settings/", "/seller/", "/admin/", "/messages"])
def test_pages_require_login(app, path):
    resp = app.test_client().get(path)
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_seller_portal_is_seller_only(app, users):
    assert client_for(app, "sam").get("/seller/").status_code == 200
    assert client_for(app, "bob").get("/seller/").status_code == 403
    assert client_for(app, "ada").get("/seller/").status_code == 403


def test_admin_portal_is_admin_only(app, users):
    assert client_for(app, "ada").get("/admin/").status_code == 200
    assert client_for(app, "bob").get("/admin/").status_code == 403
    assert client_for(app, "sam").get("/admin/").status_code == 403


def test_buyer_cannot_create_listing(app, users):
    resp = create_listing(client_for(app, "bob"))
    assert resp.status_code == 403
    with app.app_context():
        assert Listing.query.count() == 0


# ---------- Settings ----------

def test_change_display_name(app, users):
    c = client_for(app, "bob")
    c.post("/settings/", data={"name-display_name": "  Bob Lee ", "name-submit_name": "1"})
    with app.app_context():
        assert db.session.get(User, users["buyer"]).display_name == "Bob Lee"


def test_change_password_requires_current_password(app, users):
    c = client_for(app, "bob")
    resp = c.post("/settings/", data={
        "pw-current_password": "wrongpass", "pw-new_password": "newpassword1",
        "pw-confirm_new_password": "newpassword1", "pw-submit_password": "1",
    })
    assert b"Current password is incorrect" in resp.data
    c.post("/settings/", data={
        "pw-current_password": "password123", "pw-new_password": "newpassword1",
        "pw-confirm_new_password": "newpassword1", "pw-submit_password": "1",
    })
    with app.app_context():
        assert db.session.get(User, users["buyer"]).check_password("newpassword1")


# ---------- Listings and marketplace ----------

def test_create_listing_and_browse(app, users, listing_id):
    c = client_for(app, "bob")
    page = c.get("/marketplace")
    assert b"Desk lamp" in page.data
    img = c.get(f"/listings/{listing_id}/image")
    assert img.status_code == 200 and img.mimetype == "image/png"


def test_listing_validation(app, users):
    c = client_for(app, "sam")
    resp = create_listing(c, title="", price="-5")
    assert resp.status_code == 200
    fake = create_listing(c, photo=(io.BytesIO(b"not an image"), "evil.png"))
    assert b"isn&#39;t a valid" in fake.data
    with app.app_context():
        assert Listing.query.count() == 0


def test_filters_and_search(app, users):
    c = client_for(app, "sam")
    create_listing(c, title="Road bike", category="sports", price="300", shipping_fee="20",
                   photo=(io.BytesIO(PNG), "a.png"))
    create_listing(c, title="Paperback novel", category="books", price="5", location="Oakland, CA",
                   photo=(io.BytesIO(PNG), "b.png"))
    buyer = client_for(app, "bob")
    assert b"Road bike" not in buyer.get("/marketplace?q=novel").data
    assert b"Paperback novel" in buyer.get("/marketplace?category=books").data
    by_price = buyer.get("/marketplace?min_price=100").data
    assert b"Road bike" in by_price and b"Paperback" not in by_price
    no_fee = buyer.get("/marketplace?no_shipping_fee=y").data
    assert b"Paperback" in no_fee and b"Road bike" not in no_fee
    assert b"Paperback" in buyer.get("/marketplace?location=oakland").data


def test_seller_cannot_edit_others_listing(app, users, listing_id):
    c = client_for(app, "sue")
    assert c.get(f"/seller/listings/{listing_id}/edit").status_code == 404
    assert c.post(f"/seller/listings/{listing_id}/delete").status_code == 404


def test_sold_listing_hidden_from_marketplace(app, users, listing_id):
    client_for(app, "sam").post(f"/seller/listings/{listing_id}/status")
    assert b"Desk lamp" not in client_for(app, "bob").get("/marketplace").data


# ---------- Messages ----------

def test_conversation_privacy(app, users, listing_id):
    bob = client_for(app, "bob")
    bob.post(f"/messages/{listing_id}/{users['buyer']}", data={"body": "Is this available?"})
    # The seller can read and reply.
    sam = client_for(app, "sam")
    assert b"Is this available?" in sam.get(f"/messages/{listing_id}/{users['buyer']}").data
    sam.post(f"/messages/{listing_id}/{users['buyer']}", data={"body": "Yes!"})
    # Another buyer and another seller can't see it.
    assert client_for(app, "bea").get(f"/messages/{listing_id}/{users['buyer']}").status_code == 404
    assert client_for(app, "sue").get(f"/messages/{listing_id}/{users['buyer']}").status_code == 404
    with app.app_context():
        assert Message.query.count() == 2


def test_seller_cannot_start_conversation(app, users, listing_id):
    resp = client_for(app, "sam").post(f"/messages/{listing_id}/{users['buyer']}", data={"body": "Buy my lamp"})
    assert resp.status_code == 403


def test_empty_message_rejected(app, users, listing_id):
    client_for(app, "bob").post(f"/messages/{listing_id}/{users['buyer']}", data={"body": "   "})
    with app.app_context():
        assert Message.query.count() == 0


# ---------- Reviews ----------

def test_review_requires_contact_and_one_per_seller(app, users, listing_id):
    bob = client_for(app, "bob")
    assert bob.post(f"/sellers/{users['seller']}/review", data={"rating": "5", "body": "Great"}).status_code == 403
    bob.post(f"/messages/{listing_id}/{users['buyer']}", data={"body": "Hi"})
    bob.post(f"/sellers/{users['seller']}/review", data={"rating": "5", "body": "Great"})
    bob.post(f"/sellers/{users['seller']}/review", data={"rating": "3", "body": "Okay actually"})
    with app.app_context():
        review = Review.query.one()
        assert review.rating == 3


def test_seller_cannot_review(app, users):
    resp = client_for(app, "sue").post(f"/sellers/{users['seller']}/review", data={"rating": "1", "body": "Bad"})
    assert resp.status_code == 403


# ---------- Reports and moderation ----------

def test_report_flow_with_temp_ban(app, users, listing_id):
    bob = client_for(app, "bob")
    bob.post(f"/report?user={users['seller']}&listing={listing_id}", data={"reason": "scam", "details": "Asked for gift cards"})
    with app.app_context():
        report = Report.query.one()
        assert report.status == ReportStatus.OPEN
        report_id = report.id

    ada = client_for(app, "ada")
    ada.post(f"/admin/reports/{report_id}", data={
        "outcome": "temp_ban", "ban_days": "7", "remove_content": "y", "note": "Scam attempt confirmed",
    })
    with app.app_context():
        assert db.session.get(Report, report_id).status == ReportStatus.RESOLVED
        assert db.session.get(Listing, listing_id).status == ListingStatus.REMOVED
        assert ModerationAction.query.filter_by(action=ModAction.TEMP_BAN).count() == 1
        assert ModerationNote.query.count() == 1

    # Removed listing is hidden from buyers.
    assert bob.get(f"/listings/{listing_id}").status_code == 404
    # The banned seller is logged out and can't log back in.
    resp = client_for(app, "sam").get("/marketplace")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_cannot_report_self_or_admin(app, users):
    bob = client_for(app, "bob")
    assert bob.get(f"/report?user={users['buyer']}").status_code == 404
    assert bob.get(f"/report?user={users['admin']}").status_code == 404


def test_perm_ban_then_unban(app, users):
    ada = client_for(app, "ada")
    ada.post(f"/admin/users/{users['buyer']}", data={"act-action": "perm_ban", "act-reason": "Spam", "act-submit_action": "1"})
    assert "/login" in client_for(app, "bob").get("/marketplace").headers["Location"]
    ada.post(f"/admin/users/{users['buyer']}", data={"act-action": "unban", "act-reason": "Appeal accepted", "act-submit_action": "1"})
    assert client_for(app, "bob").get("/marketplace").status_code == 200


def test_expired_temp_ban_lets_user_back_in(app, users):
    with app.app_context():
        db.session.add(ModerationAction(
            target_user_id=users["buyer"], admin_id=users["admin"], action=ModAction.TEMP_BAN,
            reason="Cool off", expires_at=utcnow().replace(year=2000),
        ))
        db.session.commit()
    assert client_for(app, "bob").get("/marketplace").status_code == 200


def test_admin_cannot_moderate_admin(app, users):
    other = make_user(app, "alan", Role.ADMIN)
    resp = client_for(app, "ada").post(f"/admin/users/{other}", data={
        "act-action": "perm_ban", "act-reason": "x", "act-submit_action": "1",
    })
    assert resp.status_code == 403


def test_warning_shows_banner_until_acknowledged(app, users):
    client_for(app, "ada").post(f"/admin/users/{users['buyer']}", data={
        "act-action": "warning", "act-reason": "Be polite", "act-submit_action": "1",
    })
    bob = client_for(app, "bob")
    assert b"Be polite" in bob.get("/marketplace").data
    with app.app_context():
        warning_id = ModerationAction.query.one().id
    bob.post(f"/settings/warnings/{warning_id}/acknowledge")
    assert b"A moderator warned you" not in bob.get("/marketplace").data


def test_admin_removes_review(app, users, listing_id):
    bob = client_for(app, "bob")
    bob.post(f"/messages/{listing_id}/{users['buyer']}", data={"body": "Hi"})
    bob.post(f"/sellers/{users['seller']}/review", data={"rating": "1", "body": "Fake review"})
    with app.app_context():
        review_id = Review.query.one().id
    client_for(app, "ada").post(f"/admin/reviews/{review_id}/remove")
    with app.app_context():
        assert db.session.get(Review, review_id).status == ReviewStatus.REMOVED
    assert b"Fake review" not in client_for(app, "bea").get(f"/sellers/{users['seller']}").data


def test_admin_notes_saved(app, users):
    client_for(app, "ada").post(f"/admin/users/{users['buyer']}", data={"note-body": "Watch this account", "note-submit_note": "1"})
    with app.app_context():
        assert ModerationNote.query.one().body == "Watch this account"


def test_admin_user_search(app, users):
    resp = client_for(app, "ada").get("/admin/users?q=sa")
    assert b"@sam" in resp.data and b"@bob" not in resp.data


def test_create_admin_command(app):
    runner = app.test_cli_runner(env={"ADMIN_PASSWORD": "supersecret1"})
    result = runner.invoke(args=["create-admin", "--username", "root"])
    assert "Created admin" in result.output
    with app.app_context():
        assert User.find_by_username("root").role == Role.ADMIN
