"""
Task service — the "brain" of Module 1.

Key responsibilities:
  - Evaluating frequency rules to decide which tasks are due today.
  - Recording completions (with user attribution and timestamp).
  - Listing tasks that are still pending today.
"""
from datetime import datetime, date, time, timedelta
from sqlalchemy.orm import Session

from app.models import Task, TaskLog


# --- Helpers ---

def _today_bounds() -> tuple[datetime, datetime]:
    """
    Return the start and end of "today" in UTC, matching how completed_at is stored.

    All timestamps are in UTC. We compute the UTC day window so that the
    user's "today" lines up with the server's stored times.
    """
    now_utc = datetime.utcnow()
    start = datetime.combine(now_utc.date(), time.min)
    end = datetime.combine(now_utc.date(), time.max)
    return start, end


def is_task_due_today(task: Task, today: date | None = None) -> bool:
    """
    Decide whether a task should appear on today's list.

    This pure function takes a Task object and returns True/False.
    Pure = no DB calls, no side effects — easy to test.
    """
    if today is None:
        today = datetime.utcnow().date()

    if not task.is_active:
        return False

    config = task.frequency_config or {}
    ftype = task.frequency_type

    if ftype == "once":
        # One-off task on a specific date.
        target = config.get("date")
        if not target:
            return False
        # Stored as ISO string "YYYY-MM-DD" → parse to date.
        return date.fromisoformat(target) == today

    if ftype == "daily":
        return True

    if ftype == "weekly":
        # Single weekday, e.g. {"weekday": 0} for Monday.
        return today.weekday() == config.get("weekday")

    if ftype == "specific_days":
        # List of weekdays, e.g. {"weekdays": [0, 2, 4]} for Mon/Wed/Fri.
        return today.weekday() in config.get("weekdays", [])

    if ftype == "monthly":
        # Specific day of the month, e.g. {"day": 15} for the 15th.
        return today.day == config.get("day")
        
    return False  # Unknown frequency type — fail safe.


# --- Queries the UI will call ---

def get_pending_tasks_today(db: Session) -> list[Task]:
    """
    Return tasks that are:
      1. Due today (per their frequency rule), AND
      2. Not yet completed today.

    This is what the dashboard renders.
    """
    start, end = _today_bounds()

    # All active tasks
    candidates = db.query(Task).filter(Task.is_active.is_(True)).all()

    # Filter by "due today" using the pure function above
    due_today = [t for t in candidates if is_task_due_today(t)]

    # Find which of those have already been completed today
    completed_ids = {
        log.task_id
        for log in db.query(TaskLog)
        .filter(TaskLog.completed_at >= start, TaskLog.completed_at <= end)
        .all()
    }

    return [t for t in due_today if t.id not in completed_ids]


def get_completed_tasks_today(db: Session) -> list[TaskLog]:
    """Tasks already completed today — useful for the 'done' section of the UI."""
    start, end = _today_bounds()
    return (
        db.query(TaskLog)
        .filter(TaskLog.completed_at >= start, TaskLog.completed_at <= end)
        .order_by(TaskLog.completed_at.desc())
        .all()
    )


def complete_task(db: Session, task_id: int, user_id: int) -> TaskLog:
    """Record a completion. Returns the new TaskLog."""
    log = TaskLog(task_id=task_id, user_id=user_id, completed_at=datetime.utcnow())
    db.add(log)
    db.flush()  # Push to DB so log.id is populated, but don't commit yet
    return log


def remove_task(db: Session, task_id: int) -> None:
    """
    Soft-delete a task (sets is_active=False).

    Why soft-delete? If we hard-delete and the task has logs,
    the history disappears. Setting is_active=False keeps the
    audit trail intact while removing it from active views.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        task.is_active = False


def create_task(
    db: Session,
    name: str,
    description: str,
    frequency_type: str,
    frequency_config: dict,
) -> Task:
    """Create a new task definition."""
    task = Task(
        name=name.strip(),
        description=description.strip(),
        frequency_type=frequency_type,
        frequency_config=frequency_config,
        is_active=True,
    )
    db.add(task)
    db.flush()
    return task
