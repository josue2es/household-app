"""
User service — account management for the admin's "Usuarios" page.

From the web, admins manage manager and housekeeper accounts only
(MANAGED_ROLES). Admin accounts are managed with the Admin CLI
(`python -m app.admin`), so nobody can lock the admins out from the web.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User, ROLE_MANAGER, ROLE_HOUSEKEEPER, BCRYPT_MAX_PASSWORD_BYTES

MANAGED_ROLES = [ROLE_MANAGER, ROLE_HOUSEKEEPER]

MIN_PASSWORD_LENGTH = 6

# Quasar avatar colors that look reasonable (also used by the Admin CLI)
AVATAR_COLORS = ["red", "pink", "purple", "deep-purple", "indigo", "blue",
                 "light-blue", "cyan", "teal", "green", "amber", "orange"]


def password_problem(password: str) -> str | None:
    """Why a password can't be used (in Spanish), or None if it's fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres"
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return "La contraseña es demasiado larga"
    return None


def list_users(db: Session) -> list[User]:
    """All users: active first, then by name."""
    return db.query(User).order_by(User.is_active.desc(), User.name).all()


def create_user(db: Session, name: str, role: str, avatar_color: str, password: str) -> User:
    """Create a manager or housekeeper account. Raises ValueError with a message for the user."""
    name = name.strip()
    if not name:
        raise ValueError("Escribe un nombre")
    if role not in MANAGED_ROLES:
        raise ValueError("Rol no válido")
    if db.query(User).filter(func.lower(User.name) == name.lower()).first():
        raise ValueError(f"Ya existe un usuario llamado '{name}'")
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)

    user = User(name=name, role=role, avatar_color=avatar_color, is_active=True)
    user.set_password(password)
    db.add(user)
    db.flush()
    return user


def set_password(db: Session, user_id: int, password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    _managed_user(db, user_id).set_password(password)


def set_role(db: Session, user_id: int, role: str) -> None:
    if role not in MANAGED_ROLES:
        raise ValueError("Rol no válido")
    _managed_user(db, user_id).role = role


def set_active(db: Session, user_id: int, active: bool) -> None:
    """Deactivated users can't log in (and are logged out); their history is kept."""
    _managed_user(db, user_id).is_active = active


def _managed_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.role not in MANAGED_ROLES:
        raise ValueError("Este usuario no se puede modificar desde aquí")
    return user
