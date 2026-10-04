"""
Application entry point.

Run with:
    uv run python -m app.main

Then visit http://localhost:8080 in a browser (or the port set by
APP_PORT in .env).
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from nicegui import ui, app as nicegui_app

from app.database import init_db
from app import auth
from app.pages import login_page, tasks_page, add_task_page, groceries_page


# ---------- Routes ----------

@ui.page("/")
def index():
    """Root — redirect to /tasks (or /login if not signed in)."""
    if auth.is_authenticated():
        ui.navigate.to("/tasks")
    else:
        ui.navigate.to("/login")


@ui.page("/login")
def login():
    if auth.is_authenticated():
        ui.navigate.to("/tasks")
        return
    login_page.render()


@ui.page("/tasks")
def tasks():
    if not auth.is_authenticated():
        ui.navigate.to("/login")
        return
    tasks_page.render()


@ui.page("/tasks/new")
def new_task():
    if not auth.is_authenticated():
        ui.navigate.to("/login")
        return
    add_task_page.render()


@ui.page("/groceries")
def groceries():
    if not auth.is_authenticated():
        ui.navigate.to("/login")
        return
    groceries_page.render()


# ---------- Bootstrap ----------

# Load settings from the .env file at the project root, if there is one.
# Variables already set in the environment win over .env, so Docker's
# settings (passed in by docker-compose.yml) are never overridden.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

init_db()  # Create tables if missing

# `storage_secret` is required for app.storage.user. In production set via env var.
STORAGE_SECRET = os.environ.get("STORAGE_SECRET", "dev-secret-change-me")

# Port the web app listens on. Set APP_PORT in .env to use another one locally.
# Docker always uses 8080 inside the container; its host port is in docker-compose.yml.
APP_PORT = int(os.environ.get("APP_PORT") or 8080)

ui.run(
    host="0.0.0.0",
    port=APP_PORT,
    title="Household",
    favicon="🏠",
    storage_secret=STORAGE_SECRET,
    show=False,  # don't auto-open browser; mobile testing wants a URL
    reload=False,  # set True for dev auto-reload (slower in containers)
)