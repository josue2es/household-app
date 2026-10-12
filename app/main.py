"""
Application entry point.

Run with:
    uv run python -m app.main

Then visit http://localhost:8080 in a browser (or the port set by
APP_PORT in .env).
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi.responses import FileResponse, Response
from nicegui import ui, app as nicegui_app

from app.database import get_db, init_db
from app import auth, pwa
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_HOUSEKEEPER, TaskCheck
from app.services.check_service import KIND_PHOTO
from app.services.photo_service import photo_file
from app.pages import (
    login_page, tasks_page, add_task_page, groceries_page,
    review_page, feedback_page, users_page,
)


def _page_user(*roles: str) -> dict | None:
    """
    The logged-in user, if their role may open this page (any role when
    `roles` is empty). Otherwise redirect — to /login, or to the user's
    own home page — and return None.

    Every page checks this, and the bottom nav (NAV_BY_ROLE in
    ui_helpers.py) only links to pages the role may open.
    """
    user = auth.current_user()
    if user is None:
        auth.logout()  # forget a deleted or deactivated account
        ui.navigate.to("/login")
        return None
    if roles and user["role"] not in roles:
        ui.navigate.to(auth.home_page(user["role"]))
        return None
    return user


# ---------- Routes ----------

@ui.page("/")
def index():
    """Root — redirect to the user's home page (or /login if not signed in)."""
    user = auth.current_user()
    if user:
        ui.navigate.to(auth.home_page(user["role"]))
    else:
        ui.navigate.to("/login")


@ui.page("/login")
def login():
    user = auth.current_user()
    if user:
        ui.navigate.to(auth.home_page(user["role"]))
        return
    login_page.render()


@ui.page("/tasks")
def tasks():
    user = _page_user()
    if user:
        tasks_page.render(user)


@ui.page("/tasks/new")
def new_task():
    if _page_user(ROLE_ADMIN, ROLE_MANAGER):
        add_task_page.render()


@ui.page("/groceries")
def groceries():
    if _page_user():
        groceries_page.render()


@ui.page("/review")
def review(day: str | None = None):
    user = _page_user(ROLE_ADMIN, ROLE_MANAGER)
    if user:
        review_page.render(user, day)


@ui.page("/feedback")
def feedback():
    user = _page_user(ROLE_HOUSEKEEPER)
    if user:
        feedback_page.render(user)


@ui.page("/users")
def users():
    user = _page_user(ROLE_ADMIN)
    if user:
        users_page.render(user)


@nicegui_app.get("/photos/{check_id}", include_in_schema=False)
async def task_photo(check_id: int):
    """
    A check's photo. Photos of the house are private: only logged-in users
    get them, and the housekeeper can't see an inspection before it's rated.
    """
    user = auth.current_user()
    if user is None:
        return Response(status_code=401)
    with get_db() as db:
        check = db.get(TaskCheck, check_id)
        visible = check is not None and check.photo_path and (
            user["role"] != ROLE_HOUSEKEEPER
            or check.kind == KIND_PHOTO
            or check.rating is not None
        )
        path = photo_file(check.photo_path) if visible else None
    if path is None:
        return Response(status_code=404)
    # The URL changes with every new photo (see ui_helpers.photo_url),
    # so the browser can keep it for a week.
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=604800"})


# ---------- Bootstrap ----------

# Load settings from the .env file at the project root, if there is one.
# Variables already set in the environment win over .env, so Docker's
# settings (passed in by docker-compose.yml) are never overridden.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Print the app's own log messages (e.g. one line per photo identification,
# with its reference code) to the console, journalctl or `docker compose logs`.
# Libraries keep the default level (warnings and errors only).
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("household").setLevel(logging.INFO)

init_db()  # Create tables if missing
pwa.setup()  # Installable app: manifest, service worker, install banner

# `storage_secret` is required for app.storage.user. In production set via env var.
STORAGE_SECRET = os.environ.get("STORAGE_SECRET", "dev-secret-change-me")

# Address and port the web app listens on. Set them in .env to change them
# outside Docker: APP_HOST=127.0.0.1 accepts only connections from this machine
# (e.g. a reverse proxy like Caddy). Docker always uses 0.0.0.0:8080 inside the
# container; its host port is in docker-compose.yml.
APP_HOST = os.environ.get("APP_HOST") or "0.0.0.0"
APP_PORT = int(os.environ.get("APP_PORT") or 8080)

ui.run(
    host=APP_HOST,
    port=APP_PORT,
    title="Household",
    favicon="🏠",
    storage_secret=STORAGE_SECRET,
    show=False,  # don't auto-open browser; mobile testing wants a URL
    reload=False,  # set True for dev auto-reload (slower in containers)
)