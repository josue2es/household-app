"""
Authentication helpers.

We use NiceGUI's `app.storage.user` for session storage — it's a
per-browser dictionary that persists across page reloads.

The session only remembers *who* is logged in. Their role and whether
their account is still active are read from the database on every page
load (see `current_user`), so an admin's changes take effect right away.
"""
from nicegui import app
from app.database import get_db
from app.models import User, ROLE_ADMIN, ROLE_MANAGER, ROLE_HOUSEKEEPER

# The page each role lands on after logging in.
HOME_PAGES = {
    ROLE_ADMIN: "/tasks",
    ROLE_MANAGER: "/review",
    ROLE_HOUSEKEEPER: "/tasks",
}


def login(user_data: dict) -> None:
    """Mark the user as logged in for this browser session."""
    app.storage.user["user_id"] = user_data["id"]
    app.storage.user["user_name"] = user_data["name"]
    app.storage.user["avatar_color"] = user_data["avatar_color"]


def logout() -> None:
    """Clear the session."""
    app.storage.user.clear()


def is_authenticated() -> bool:
    return current_user() is not None


def current_user_id() -> int | None:
    return app.storage.user.get("user_id")


def current_user_name() -> str | None:
    return app.storage.user.get("user_name")


def current_avatar_color() -> str:
    return app.storage.user.get("avatar_color", "blue")


def current_user() -> dict | None:
    """
    The logged-in user as a dict (id, name, avatar_color, role), or None
    if nobody is logged in or their account was deleted or deactivated.
    """
    user_id = current_user_id()
    if user_id is None:
        return None
    with get_db() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return _user_dict(user)


def home_page(role: str) -> str:
    return HOME_PAGES.get(role, "/tasks")


def authenticate(username: str, password: str) -> dict | None:
    """
    Verify credentials. Returns a dict of user data on success, None on failure.

    Why a dict instead of the User object? Because the DB session closes
    at the end of this function. If we returned the User object, accessing
    user.id later would crash with DetachedInstanceError — the object is
    no longer connected to a session that can load its data.
    """
    with get_db() as db:
        user = db.query(User).filter(User.name == username, User.is_active.is_(True)).first()
        if user and user.check_password(password):
            # Copy what we need INTO A PLAIN DICT while session is still open
            return _user_dict(user)
    return None


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "avatar_color": user.avatar_color,
        "role": user.role,
    }


def list_users() -> list[tuple[int, str, str]]:
    """For the login dropdown: returns [(id, name, color), ...] of active users."""
    with get_db() as db:
        users = db.query(User).filter(User.is_active.is_(True)).order_by(User.name).all()
        return [(u.id, u.name, u.avatar_color) for u in users]
