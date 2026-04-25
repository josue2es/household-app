"""
Database connection and session management.

This module sets up the SQLAlchemy "engine" (the connection to SQLite)
and provides a way to get a "session" (a temporary workspace for queries).
"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

# --- File location ---
# The DB file lives in the `data/` folder at the project root.
# We use Path so it works on Windows AND Linux (the VPS).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)  # Create the folder if it doesn't exist
DB_PATH = DATA_DIR / "household.db"

# --- The Engine ---
# This is the low-level connection pool to SQLite.
# `check_same_thread=False` is needed because NiceGUI handles
# requests in different threads, and SQLite is conservative by default.
DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # Set True to see every SQL query in the console (great for debugging!)
)

# --- The Session Factory ---
# `SessionLocal()` produces a fresh session whenever called.
# A session = a unit of work = a temporary "scratchpad" for DB operations.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- The Base Class ---
# All our model classes (Users, Tasks, etc.) will inherit from this.
# It's how SQLAlchemy knows "this Python class maps to a DB table."
Base = declarative_base()


@contextmanager
def get_db():
    """
    Context manager for database sessions.

    Usage:
        with get_db() as db:
            users = db.query(User).all()

    Why a context manager? It guarantees the session is closed even
    if an error happens — preventing connection leaks.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()  # Save changes if no errors
    except Exception:
        db.rollback()  # Undo changes if something went wrong
        raise
    finally:
        db.close()  # Always release the connection


def init_db():
    """Create all tables defined in models.py. Safe to run multiple times."""
    # Import models here so SQLAlchemy "sees" them before creating tables.
    # (Avoiding circular imports is why we do it here, not at the top.)
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print(f"✓ Database ready at {DB_PATH}")