from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired, FileSize
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange, Optional, ValidationError

from app.market.models import CATEGORIES, REPORT_REASONS

IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _strip(value):
    return value.strip() if isinstance(value, str) else value


# ---------- Settings ----------

class DisplayNameForm(FlaskForm):
    display_name = StringField(
        "Display name",
        filters=[_strip],
        validators=[DataRequired(message="Display name cannot be blank."), Length(max=50)],
    )
    submit_name = SubmitField("Save display name")


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_new_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )
    submit_password = SubmitField("Change password")


# ---------- Listings ----------

class ListingForm(FlaskForm):
    title = StringField("Title", filters=[_strip], validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Description", filters=[_strip], validators=[DataRequired(), Length(max=2000)])
    category = SelectField("Category", choices=CATEGORIES, validators=[DataRequired()])
    price = DecimalField(
        "Price ($)", places=2,
        validators=[DataRequired(message="Enter a price."), NumberRange(min=0.01, max=100000)],
    )
    shipping_fee = DecimalField(
        "Shipping fee ($)", places=2,
        validators=[Optional(), NumberRange(min=0, max=10000)],
        description="Leave blank if there's no shipping fee.",
    )
    location = StringField(
        "Location", filters=[_strip], validators=[DataRequired(), Length(max=100)],
        description="City or neighborhood, for example San Jose, CA.",
    )
    photo = FileField(
        "Photo",
        validators=[
            FileAllowed(IMAGE_EXTENSIONS, "Photos must be JPG, PNG, or WebP."),
            FileSize(max_size=MAX_IMAGE_BYTES, message="Photos must be 2 MB or smaller."),
        ],
    )
    submit = SubmitField("Save listing")

    def __init__(self, *args, require_photo=True, **kwargs):
        super().__init__(*args, **kwargs)
        if require_photo:
            self.photo.validators = [FileRequired("Add a photo of the item.")] + list(self.photo.validators)


class MarketFilterForm(FlaskForm):
    class Meta:
        csrf = False  # GET search form

    q = StringField("Search", filters=[_strip])
    category = SelectField("Category", choices=[("", "All categories")] + CATEGORIES, validators=[Optional()])
    min_price = DecimalField("Min price", validators=[Optional(), NumberRange(min=0)])
    max_price = DecimalField("Max price", validators=[Optional(), NumberRange(min=0)])
    location = StringField("Location", filters=[_strip])
    no_shipping_fee = BooleanField("No shipping fee")
    sort = SelectField(
        "Sort by",
        choices=[("newest", "Newest"), ("price_asc", "Price: low to high"), ("price_desc", "Price: high to low")],
        default="newest",
    )


# ---------- Messages, reviews, reports ----------

class MessageForm(FlaskForm):
    body = TextAreaField("Message", filters=[_strip], validators=[DataRequired(message="Write a message."), Length(max=2000)])
    submit = SubmitField("Send")


class ReviewForm(FlaskForm):
    rating = SelectField(
        "Rating",
        choices=[("5", "5 stars"), ("4", "4 stars"), ("3", "3 stars"), ("2", "2 stars"), ("1", "1 star")],
        coerce=int,
    )
    body = TextAreaField("Review", filters=[_strip], validators=[DataRequired(message="Write a review."), Length(max=1000)])
    submit = SubmitField("Post review")


class ReportForm(FlaskForm):
    reason = SelectField("Reason", choices=REPORT_REASONS, validators=[DataRequired()])
    details = TextAreaField(
        "What happened?", filters=[_strip],
        validators=[DataRequired(message="Describe what happened."), Length(max=2000)],
    )
    submit = SubmitField("Send report")


# ---------- Admin ----------

class UserModerationForm(FlaskForm):
    action = SelectField(
        "Action",
        choices=[
            ("warning", "Warn"),
            ("temp_ban", "Temporary ban"),
            ("perm_ban", "Permanent ban"),
            ("unban", "Lift ban"),
        ],
    )
    ban_days = IntegerField("Ban length in days", validators=[Optional(), NumberRange(min=1, max=365)])
    reason = TextAreaField("Reason shown to the user", filters=[_strip], validators=[DataRequired(), Length(max=1000)])
    submit_action = SubmitField("Apply action")

    def validate_ban_days(self, field):
        if self.action.data == "temp_ban" and not field.data:
            raise ValidationError("Enter how many days the ban lasts.")


class NoteForm(FlaskForm):
    body = TextAreaField("Moderation note", filters=[_strip], validators=[DataRequired(), Length(max=2000)])
    submit_note = SubmitField("Add note")


class ReportResolveForm(FlaskForm):
    outcome = SelectField(
        "Outcome",
        choices=[
            ("dismiss", "Dismiss, no violation"),
            ("content_only", "Remove the reported content only"),
            ("warning", "Warn the user"),
            ("temp_ban", "Temporary ban"),
            ("perm_ban", "Permanent ban"),
        ],
    )
    ban_days = IntegerField("Ban length in days", validators=[Optional(), NumberRange(min=1, max=365)])
    remove_content = BooleanField("Also remove the reported listing or review")
    note = TextAreaField(
        "Reason and notes", filters=[_strip], validators=[DataRequired(), Length(max=2000)],
        description="Saved as a moderation note. For warnings and bans it's also shown to the user as the reason.",
    )
    submit = SubmitField("Close report")

    def validate_ban_days(self, field):
        if self.outcome.data == "temp_ban" and not field.data:
            raise ValidationError("Enter how many days the ban lasts.")
