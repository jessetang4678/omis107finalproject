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

## Stage 2: marketplace, messaging, seller portal, admin portal

### Pages

| Page | URL | Who can use it |
|---|---|---|
| Marketplace with search and filters | `/marketplace` | Everyone with a role |
| Listing detail | `/listings/<id>` | Everyone; removed listings only for the seller and admins |
| Seller profile and reviews | `/sellers/<id>` | Everyone; only buyers can review |
| Messages inbox and conversations | `/messages` | Buyers and sellers in that conversation; admins can read |
| Report a user, listing, or review | `/report` | Buyers and sellers |
| Settings | `/settings/` | Everyone with a role |
| Seller portal | `/seller/` | Sellers only |
| Admin portal: reports inbox and user search | `/admin/` | Admins only |

### Rules the server enforces

- Sellers can only edit, mark sold, or delete their own listings. Another seller's listing returns a 404.
- Listing photos must be real JPG, PNG, or WebP files of 2 MB or less, checked by the file's contents, not its name. Photos are stored in the database so they survive redeploys.
- Buyers start conversations about active listings. Sellers can only reply to conversations a buyer started.
- A buyer can review a seller once, only after messaging them. Posting again updates the review.
- Users can't report themselves or admins, and a duplicate open report is ignored.
- Admins can warn, temporarily ban, permanently ban, or lift a ban, and can remove listings and reviews. Admins can't moderate other admins.
- A banned user is logged out on their next request and can't log back in until the ban ends. Warnings appear as a banner until the user dismisses them.
- Moderation notes are only visible to admins.

### Creating the first admin

```bash
flask --app run create-admin --username admin
```

It prompts for a password, or reads `ADMIN_PASSWORD` from the environment.

### Known limitations

- Location filtering matches text, so "San Jose" finds listings in San Jose but there's no distance search.
- Messages don't update live; refresh the page to see new replies.
- New tables are added by `db.create_all()`, which can't change columns on existing tables. Any later change to an existing table needs a migration tool such as Flask-Migrate.
