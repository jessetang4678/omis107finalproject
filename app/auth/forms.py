import re

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError

from app.models import User

WHITESPACE = re.compile(r"\s")


class SignupForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=30)],
        description="Unique, no spaces. This can't be changed later.",
    )
    display_name = StringField(
        "Display name",
        validators=[DataRequired(), Length(min=1, max=50)],
        description="What other people see. Spaces are fine; you can change it later.",
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create account")

    def validate_username(self, field):
        if WHITESPACE.search(field.data):
            raise ValidationError("Username cannot contain spaces.")
        if User.find_by_username(field.data):
            raise ValidationError("That username is already taken.")

    def validate_display_name(self, field):
        field.data = field.data.strip()
        if not field.data:
            raise ValidationError("Display name cannot be blank.")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")
