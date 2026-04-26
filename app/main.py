"""
Application entry point.

Run with:
    python -m app.main

Then visit http://localhost:8080 in a browser.
"""
import os
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

init_db()  # Create tables if missing

# `storage_secret` is required for app.storage.user. In production set via env var.
STORAGE_SECRET = os.environ.get("STORAGE_SECRET", "dev-secret-change-me")

ui.run(
    host="0.0.0.0",
    port=8080,
    title="Household",
    favicon="🏠",
    storage_secret=STORAGE_SECRET,
    show=False,  # don't auto-open browser; mobile testing wants a URL
    reload=False,  # set True for dev auto-reload (slower in containers)
)