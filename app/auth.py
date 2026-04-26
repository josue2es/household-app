"""
Authentication helpers.

We use NiceGUI's `app.storage.user` for session storage — it's a
per-browser-tab dictionary that persists across page reloads.
"""
from nicegui import app
from app.database import get_db
from app.models import User


def login(user_data: dict) -> None:
    """Mark the user as logged in for this browser session."""
    app.storage.user["user_id"] = user_data["id"]
    app.storage.user["user_name"] = user_data["name"]
    app.storage.user["avatar_color"] = user_data["avatar_color"]


def logout() -> None:
    """Clear the session."""
    app.storage.user.clear()


def is_authenticated() -> bool:
    return "user_id" in app.storage.user


def current_user_id() -> int | None:
    return app.storage.user.get("user_id")


def current_user_name() -> str | None:
    return app.storage.user.get("user_name")


def current_avatar_color() -> str:
    return app.storage.user.get("avatar_color", "blue")


def authenticate(username: str, password: str) -> dict | None:
    """
    Verify credentials. Returns a dict of user data on success, None on failure.

    Why a dict instead of the User object? Because the DB session closes
    at the end of this function. If we returned the User object, accessing
    user.id later would crash with DetachedInstanceError — the object is
    no longer connected to a session that can load its data.
    """
    with get_db() as db:
        user = db.query(User).filter(User.name == username).first()
        if user and user.check_password(password):
            # Copy what we need INTO A PLAIN DICT while session is still open
            return {
                "id": user.id,
                "name": user.name,
                "avatar_color": user.avatar_color,
            }
    return None

def list_users() -> list[tuple[int, str, str]]:
    """For the login dropdown: returns [(id, name, color), ...]."""
    with get_db() as db:
        return [(u.id, u.name, u.avatar_color) for u in db.query(User).all()]