"""
Database models — Python classes that map to SQLite tables.

Each class = one table. Each class attribute = one column.
SQLAlchemy generates the SQL for us automatically.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, JSON, Text
)
from sqlalchemy.orm import relationship
import bcrypt

from app.database import Base


# ============================================================
# USERS
# ============================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    avatar_color = Column(String(20), default="blue")  # for UI badges
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships — let us do `user.task_logs` to get all their completions
    task_logs = relationship("TaskLog", back_populates="user")
    shopping_additions = relationship("ActiveShoppingItem", back_populates="added_by")

    # --- Password helpers (encapsulating bcrypt here keeps the rest of the code clean) ---
    def set_password(self, plain_password: str) -> None:
        """Hash and store the password. Never store the plain text."""
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")

    def check_password(self, plain_password: str) -> bool:
        """Verify a login attempt against the stored hash."""
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            self.password_hash.encode("utf-8"),
        )

    def __repr__(self):
        return f"<User {self.name}>"


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