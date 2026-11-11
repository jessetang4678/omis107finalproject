from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


class Role:
    """User types. Admin exists in the model but cannot be chosen at sign up."""

    BUYER = "buyer"
    SELLER = "seller"
    ADMIN = "admin"

    SELECTABLE = (BUYER, SELLER)
    ALL = (BUYER, SELLER, ADMIN)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    # Usernames are unique case-insensitively (see username_lower) and never change.
    username = db.Column(db.String(30), nullable=False)
    username_lower = db.Column(db.String(30), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # None until the user picks buyer or seller after creating their account.
    role = db.Column(db.String(10), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __init__(self, username, display_name, password):
        self.username = username
        self.username_lower = username.lower()
        self.display_name = display_name
        self.set_password(password)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def has_role(self):
        return self.role is not None

    @classmethod
    def find_by_username(cls, username):
        return cls.query.filter_by(username_lower=username.strip().lower()).first()

    def __repr__(self):
        return f"<User {self.username} ({self.role or 'no role'})>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
