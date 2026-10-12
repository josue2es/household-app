"""
Database models — Python classes that map to SQLite tables.

Each class = one table. Each class attribute = one column.
SQLAlchemy generates the SQL for us automatically.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Boolean, ForeignKey, JSON, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
import bcrypt

from app.database import Base

# bcrypt only uses the first 72 bytes of a password. bcrypt 5 raises
# ValueError for longer input instead of silently ignoring the rest.
# (Accented letters like "ñ" take 2 bytes in UTF-8.)
BCRYPT_MAX_PASSWORD_BYTES = 72

# User roles. Each one decides which pages a user can open (see app/main.py).
ROLE_ADMIN = "admin"              # sees everything, creates manager/housekeeper accounts
ROLE_MANAGER = "manager"          # reviews the housekeeper's work
ROLE_HOUSEKEEPER = "housekeeper"  # does the chores, proves 2 of them with a photo each day
ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_HOUSEKEEPER]

# How each role is called in the UI.
ROLE_LABELS = {
    ROLE_ADMIN: "Administrador",
    ROLE_MANAGER: "Supervisor",
    ROLE_HOUSEKEEPER: "Ama de llaves",
}


# ============================================================
# USERS
# ============================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    avatar_color = Column(String(20), default="blue")  # for UI badges
    # One of ROLES. Users that existed before roles were added became admins
    # (see _add_missing_columns in database.py).
    role = Column(String(20), nullable=False, default=ROLE_HOUSEKEEPER)
    # Deactivated users can't log in, but their history is kept.
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships — let us do `user.task_logs` to get all their completions
    task_logs = relationship("TaskLog", back_populates="user")
    shopping_additions = relationship("ActiveShoppingItem", back_populates="added_by")

    # --- Password helpers (encapsulating bcrypt here keeps the rest of the code clean) ---
    def set_password(self, plain_password: str) -> None:
        """
        Hash and store the password. Never store the plain text.
        Raises ValueError if it is longer than BCRYPT_MAX_PASSWORD_BYTES.
        """
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")

    def check_password(self, plain_password: str) -> bool:
        """Verify a login attempt against the stored hash."""
        # Truncate to bcrypt's limit, as bcrypt < 5 did silently: hashes of
        # longer passwords created back then keep working, and an over-long
        # login attempt just fails instead of raising ValueError.
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES],
            self.password_hash.encode("utf-8"),
        )

    def __repr__(self):
        return f"<User {self.name} ({self.role})>"


# ============================================================
# TASKS  (the "template" — recurring rules)
# ============================================================
class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")

    # Frequency rules — see task_service.py for evaluation logic
    # Possible values: "once", "daily", "weekly", "specific_days"
    frequency_type = Column(String(20), nullable=False, default="once")

    # JSON config holding the details. Examples:
    #   "once":          {"date": "2026-05-01"}
    #   "daily":         {}
    #   "weekly":        {"weekday": 1}   (0=Monday, 6=Sunday)
    #   "specific_days": {"weekdays": [0, 2, 4]}  (Mon, Wed, Fri)
    frequency_config = Column(JSON, default=dict)

    is_active = Column(Boolean, default=True)  # Soft-delete flag
    created_at = Column(DateTime, default=datetime.utcnow)

    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Task {self.name} ({self.frequency_type})>"


# ============================================================
# TASK_LOGS  (history of completions)
# ============================================================
class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow, index=True)

    task = relationship("Task", back_populates="logs")
    user = relationship("User", back_populates="task_logs")


# ============================================================
# TASK_CHECKS  (tasks drawn at random each day for a quality check)
# ============================================================
class TaskCheck(Base):
    """
    One task picked at random to be checked on a given day.

    kind = "photo":      the housekeeper proves the task with a photo,
                         then a manager rates it.
    kind = "inspection": a manager inspects the task in person, takes a
                         photo and rates it. The housekeeper doesn't see
                         it until it has been rated.

    See app/services/check_service.py for the rules.
    """
    __tablename__ = "task_checks"
    __table_args__ = (
        # `slot` (1, 2, ...) numbers the checks of one kind on one day. If two
        # processes draw the same day at the same moment, the second insert
        # breaks this constraint and is rolled back, so a day is drawn once.
        UniqueConstraint("day", "kind", "slot"),
        UniqueConstraint("day", "task_id"),  # never the same task twice a day
    )

    id = Column(Integer, primary_key=True)
    day = Column(Date, nullable=False, index=True)  # local calendar day (LOCAL_TZ)
    kind = Column(String(20), nullable=False)
    slot = Column(Integer, nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)

    # The photo: the housekeeper's proof, or the manager's inspection photo.
    # Path relative to data/photos/ (see app/services/photo_service.py).
    photo_path = Column(String(200), nullable=True)
    photo_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    photo_at = Column(DateTime, nullable=True)

    # The manager's review.
    rating = Column(Integer, nullable=True)  # 1-5 stars; None = not reviewed yet
    comment = Column(Text, default="")
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    # When the housekeeper opened the review (None = not seen yet).
    seen_at = Column(DateTime, nullable=True)

    task = relationship("Task")
    photo_by = relationship("User", foreign_keys=[photo_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])

    def __repr__(self):
        return f"<TaskCheck {self.day} {self.kind}#{self.slot} task={self.task_id}>"


# ============================================================
# GROCERY_ITEMS  (the "library" of all known items)
# ============================================================
class GroceryItem(Base):
    __tablename__ = "grocery_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), default="Food")  # Food, Groceries, House, Pet, etc.

    # The magic field — drives the "most-bought first" sorting
    purchase_count = Column(Integer, default=0)
    last_purchased_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shopping_entries = relationship("ActiveShoppingItem", back_populates="item")

    def __repr__(self):
        return f"<GroceryItem {self.name} (bought {self.purchase_count}x)>"


# ============================================================
# ACTIVE_SHOPPING_LIST  (current pending list)
# ============================================================
class ActiveShoppingItem(Base):
    __tablename__ = "active_shopping_list"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("grocery_items.id"), nullable=False)
    added_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    added_at = Column(DateTime, default=datetime.utcnow)
    is_purchased = Column(Boolean, default=False, index=True)
    purchased_at = Column(DateTime, nullable=True)

    item = relationship("GroceryItem", back_populates="shopping_entries")
    added_by = relationship("User", back_populates="shopping_additions")