# Marketplace (stage 1: accounts)

A Flask marketplace where buyers purchase items from sellers and administrators
moderate. This stage covers **sign up, log in, log out, and choosing buyer or
seller**. Settings, the marketplace, the seller portal and the admin portal are
not built yet.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000. The SQLite database is created automatically at
`instance/marketplace.db`. For anything beyond local development, set a real
`SECRET_KEY` environment variable.

Run the tests with `pytest`.

## What's implemented

- **Sign up** (`/signup`): username, display name, password (+ confirmation).
  - Username: unique (case-insensitive, so `Alice` and `alice` clash), 3–30
    characters, no spaces. Stored but never editable.
  - Display name: up to 50 characters, spaces allowed, not unique.
  - Password: at least 8 characters, stored hashed.
- **Log in** (`/login`) and **log out** (POST `/logout`).
- **Role picker** (`/choose-role`): shown as a modal with no close button right
  after sign up. Until a user picks Buyer or Seller, every protected page sends
  them back to it, including after logging out and back in. The choice is made
  once and can't be changed through this page.
- **Placeholder home page** (`/home`): proves the gate works; the marketplace
  will replace it.

The `admin` role exists in the data model but can't be chosen at sign up.

## Project layout

```
run.py              entry point
config.py           settings (dev + test)
app/__init__.py     app factory, database, login manager, CSRF
app/models.py       User model and roles
app/decorators.py   @role_chosen_required — use on every future page
app/auth/           sign up, log in, log out, role picker
app/main/           index redirect and placeholder home
app/templates/      Jinja templates
app/static/css/     styles
tests/              pytest suite
```

## Adding the next pages

Protect each new page with `@role_chosen_required` (it also requires login).
For seller-only or admin-only pages, add a check on `current_user.role`
alongside it.
