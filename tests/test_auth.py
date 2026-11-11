import pytest

from app import create_app, db
from app.models import User
from config import TestConfig


@pytest.fixture
def app():
    app = create_app(TestConfig)
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def signup(client, username="alice", display_name="Alice Smith", password="password123", confirm=None):
    return client.post(
        "/signup",
        data={
            "username": username,
            "display_name": display_name,
            "password": password,
            "confirm_password": confirm or password,
        },
    )


def login(client, username="alice", password="password123"):
    return client.post("/login", data={"username": username, "password": password})


def logout(client):
    return client.post("/logout")


def test_root_redirects_to_login_when_signed_out(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_home_requires_login(client):
    resp = client.get("/home")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_signup_creates_user_and_goes_to_role_picker(client, app):
    resp = signup(client)
    assert resp.status_code == 302
    assert "/choose-role" in resp.headers["Location"]
    with app.app_context():
        user = User.find_by_username("alice")
        assert user.display_name == "Alice Smith"
        assert user.role is None
        assert user.password_hash != "password123"


def test_username_cannot_contain_spaces(client):
    resp = signup(client, username="alice smith")
    assert resp.status_code == 200
    assert b"cannot contain spaces" in resp.data


def test_username_must_be_unique_case_insensitive(client):
    signup(client)
    logout(client)
    resp = signup(client, username="ALICE", display_name="Another")
    assert b"already taken" in resp.data


def test_display_name_need_not_be_unique(client, app):
    signup(client, username="alice", display_name="Sam Lee")
    logout(client)
    signup(client, username="bob", display_name="Sam Lee")
    with app.app_context():
        assert User.query.filter_by(display_name="Sam Lee").count() == 2


def test_passwords_must_match(client):
    resp = signup(client, password="password123", confirm="different123")
    assert b"Passwords must match" in resp.data


def test_cannot_skip_role_choice(client):
    signup(client)
    resp = client.get("/home")
    assert resp.status_code == 302
    assert "/choose-role" in resp.headers["Location"]


def test_role_required_again_after_closing_and_logging_back_in(client):
    signup(client)
    logout(client)  # left before choosing
    resp = login(client)
    assert "/choose-role" in resp.headers["Location"]
    assert "/choose-role" in client.get("/").headers["Location"]


def test_invalid_role_rejected(client, app):
    signup(client)
    resp = client.post("/choose-role", data={"role": "admin"})
    assert resp.status_code == 200
    assert b"Please choose Buyer or Seller" in resp.data
    with app.app_context():
        assert User.find_by_username("alice").role is None


@pytest.mark.parametrize("role", ["buyer", "seller"])
def test_choosing_role_unlocks_home(client, app, role):
    signup(client)
    resp = client.post("/choose-role", data={"role": role})
    assert "/home" in resp.headers["Location"]
    assert client.get("/home").status_code == 200
    with app.app_context():
        assert User.find_by_username("alice").role == role


def test_role_cannot_be_changed_after_choosing(client, app):
    signup(client)
    client.post("/choose-role", data={"role": "buyer"})
    client.post("/choose-role", data={"role": "seller"})
    with app.app_context():
        assert User.find_by_username("alice").role == "buyer"


def test_login_with_wrong_password(client):
    signup(client)
    client.post("/choose-role", data={"role": "buyer"})
    logout(client)
    resp = login(client, password="wrongpassword")
    assert resp.status_code == 200
    assert b"Incorrect username or password" in resp.data


def test_login_success_after_role_chosen(client):
    signup(client)
    client.post("/choose-role", data={"role": "seller"})
    logout(client)
    resp = login(client, username="Alice")  # username lookup is case-insensitive
    assert "/home" in resp.headers["Location"]


def test_login_ignores_offsite_next(client):
    signup(client)
    client.post("/choose-role", data={"role": "buyer"})
    logout(client)
    resp = client.post(
        "/login?next=https://evil.example.com",
        data={"username": "alice", "password": "password123"},
    )
    assert resp.headers["Location"].endswith("/home")
