"""
Task service — the "brain" of Module 1.

Key responsibilities:
  - Evaluating frequency rules to decide which tasks are due today.
  - Recording completions (with user attribution and timestamp).
  - Listing tasks that are still pending today.
"""
from datetime import datetime, date, time, timedelta, timezone
from sqlalchemy.orm import Session

from app.models import Task, TaskLog

# Local timezone used both here (for determining "today") and in the UI (for display).
# All DB timestamps are stored as UTC-naive; we convert boundaries before comparing.
LOCAL_TZ = timezone(timedelta(hours=-6))

# Frequency types that target a specific date/day vs. flexible "any day this period" types.
SPECIFIC_DATE_TYPES = {"once", "daily", "weekly", "specific_days", "monthly"}
FLEXIBLE_TYPES = {"weekly_any", "monthly_any", "bimonthly_any", "every_x_days"}


# --- Helpers ---

def _local_date_to_utc_bounds(d: date) -> tuple[datetime, datetime]:
    """Convert a local calendar date to UTC-naive start/end for DB queries."""
    start = datetime.combine(d, time.min, tzinfo=LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    end = datetime.combine(d, time.max, tzinfo=LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    return start, end


def _today_bounds() -> tuple[datetime, datetime]:
    """Return UTC-naive start/end of the user's current local day."""
    return _local_date_to_utc_bounds(datetime.now(LOCAL_TZ).date())


def _period_bounds(ftype: str, today: date, config: dict | None = None) -> tuple[datetime, datetime]:
    """
    Return the UTC-naive completion window for a task based on its frequency type.

    Specific-date tasks only care about today; flexible tasks care about the
    whole week, month, two-month block, or X-day rolling window so a single
    completion hides the task for the rest of the period.
    """
    config = config or {}

    if ftype in SPECIFIC_DATE_TYPES:
        return _local_date_to_utc_bounds(today)

    if ftype == "weekly_any":
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=6)             # Sunday
        start, _ = _local_date_to_utc_bounds(week_start)
        _, end = _local_date_to_utc_bounds(week_end)
        return start, end

    if ftype == "monthly_any":
        month_start = today.replace(day=1)
        if today.month == 12:
            month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
        start, _ = _local_date_to_utc_bounds(month_start)
        _, end = _local_date_to_utc_bounds(month_end)
        return start, end

    if ftype == "bimonthly_any":
        # Fixed two-month blocks: Jan-Feb, Mar-Apr, May-Jun, Jul-Aug, Sep-Oct, Nov-Dec
        block_start_month = ((today.month - 1) // 2) * 2 + 1
        block_end_month = block_start_month + 1
        period_start = date(today.year, block_start_month, 1)
        if block_end_month == 12:
            period_end = date(today.year, 12, 31)
        else:
            period_end = date(today.year, block_end_month + 1, 1) - timedelta(days=1)
        start, _ = _local_date_to_utc_bounds(period_start)
        _, end = _local_date_to_utc_bounds(period_end)
        return start, end

    if ftype == "every_x_days":
        # Task is hidden for X days after the last completion.
        # Window = [today - (X-1), today]: if any completion falls here, it's still done.
        x = max(config.get("days", 1), 1)
        period_start = today - timedelta(days=x - 1)
        start, _ = _local_date_to_utc_bounds(period_start)
        _, end = _local_date_to_utc_bounds(today)
        return start, end

    # Fallback: treat as today-only
    return _local_date_to_utc_bounds(today)


def _period_end_date(ftype: str, today: date, config: dict) -> date | None:
    """Last calendar day of the current period. Returns None for every_x_days (no fixed deadline)."""
    if ftype == "weekly_any":
        return today + timedelta(days=6 - today.weekday())  # Sunday of current week
    if ftype == "monthly_any":
        if today.month == 12:
            return date(today.year + 1, 1, 1) - timedelta(days=1)
        return date(today.year, today.month + 1, 1) - timedelta(days=1)
    if ftype == "bimonthly_any":
        block_start_month = ((today.month - 1) // 2) * 2 + 1
        block_end_month = block_start_month + 1
        if block_end_month == 12:
            return date(today.year, 12, 31)
        return date(today.year, block_end_month + 1, 1) - timedelta(days=1)
    return None


def _prev_period_utc_bounds(ftype: str, today: date) -> tuple[datetime, datetime] | None:
    """UTC-naive bounds for the period immediately before the current one. None for every_x_days."""
    if ftype == "weekly_any":
        week_start = today - timedelta(days=today.weekday())  # Monday of this week
        prev_end = week_start - timedelta(days=1)             # Sunday of last week
        prev_start = prev_end - timedelta(days=6)             # Monday of last week
        s, _ = _local_date_to_utc_bounds(prev_start)
        _, e = _local_date_to_utc_bounds(prev_end)
        return s, e
    if ftype == "monthly_any":
        first_of_month = today.replace(day=1)
        prev_end = first_of_month - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        s, _ = _local_date_to_utc_bounds(prev_start)
        _, e = _local_date_to_utc_bounds(prev_end)
        return s, e
    if ftype == "bimonthly_any":
        block_start_month = ((today.month - 1) // 2) * 2 + 1
        block_start = date(today.year, block_start_month, 1)
        prev_end = block_start - timedelta(days=1)
        prev_block_start_month = ((prev_end.month - 1) // 2) * 2 + 1
        prev_start = date(prev_end.year, prev_block_start_month, 1)
        s, _ = _local_date_to_utc_bounds(prev_start)
        _, e = _local_date_to_utc_bounds(prev_end)
        return s, e
    return None


def get_flexible_urgency(
    db: Session, tasks: list[Task], today: date
) -> dict[int, tuple[int | None, bool]]:
    """
    For a list of flexible pending tasks, return display metadata.
    Returns {task_id: (days_remaining, is_overdue)}.

    days_remaining: calendar days until the end of the current period.
                    None for every_x_days which has no fixed deadline.
    is_overdue:     True when the task existed during the previous period
                    but had no completion logged in that period.
    """
    result: dict[int, tuple[int | None, bool]] = {}

    for task in tasks:
        ftype = task.frequency_type
        config = task.frequency_config or {}

        if ftype not in FLEXIBLE_TYPES:
            continue

        end_date = _period_end_date(ftype, today, config)
        days_remaining = (end_date - today).days if end_date is not None else None

        is_overdue = False
        prev_bounds = _prev_period_utc_bounds(ftype, today)
        if prev_bounds:
            prev_start, prev_end = prev_bounds
            task_created = task.created_at  # stored as UTC-naive
            if task_created is not None and task_created <= prev_end:
                done_in_prev = (
                    db.query(TaskLog)
                    .filter(
                        TaskLog.task_id == task.id,
                        TaskLog.completed_at >= prev_start,
                        TaskLog.completed_at <= prev_end,
                    )
                    .first()
                )
                if not done_in_prev:
                    is_overdue = True

        result[task.id] = (days_remaining, is_overdue)

    return result


def is_task_due_today(task: Task, today: date | None = None) -> bool:
    """
    Decide whether a task should appear on today's list.

    Flexible types (weekly_any, monthly_any, bimonthly_any) always return True —
    the completion-period check in get_pending_tasks_today handles hiding them
    once they've been done within their window.
    """
    if today is None:
        today = datetime.now(LOCAL_TZ).date()

    if not task.is_active:
        return False

    ftype = task.frequency_type

    if ftype in FLEXIBLE_TYPES:
        return True

    config = task.frequency_config or {}

    if ftype == "once":
        target = config.get("date")
        if not target:
            return False
        return date.fromisoformat(target) == today

    if ftype == "daily":
        return True

    if ftype == "weekly":
        return today.weekday() == config.get("weekday")

    if ftype == "specific_days":
        return today.weekday() in config.get("weekdays", [])

    if ftype == "monthly":
        return today.day == config.get("day")

    return False  # Unknown frequency type — fail safe.


# --- Queries the UI will call ---

def get_pending_tasks_today(db: Session) -> list[Task]:
    """
    Return tasks that are due today and not yet completed within their period,
    ordered: specific-date tasks first, flexible tasks second.
    """
    today = datetime.now(LOCAL_TZ).date()
    candidates = db.query(Task).filter(Task.is_active.is_(True)).all()
    due_today = [t for t in candidates if is_task_due_today(t, today)]

    # For each task check completion against its own period (not just today).
    pending = []
    for task in due_today:
        period_start, period_end = _period_bounds(task.frequency_type, today, task.frequency_config or {})
        already_done = db.query(TaskLog).filter(
            TaskLog.task_id == task.id,
            TaskLog.completed_at >= period_start,
            TaskLog.completed_at <= period_end,
        ).first()
        if not already_done:
            pending.append(task)

    # Specific-date tasks first, flexible "any day" tasks after.
    pending.sort(key=lambda t: t.frequency_type in FLEXIBLE_TYPES)
    return pending


def get_completed_tasks_for_today(db: Session) -> list[tuple[Task, TaskLog]]:
    """
    Return (Task, most-recent TaskLog) for every task that is due today but
    already completed within its own period. Ordered same as pending: specific
    date tasks first, flexible tasks after.
    """
    today = datetime.now(LOCAL_TZ).date()
    candidates = db.query(Task).filter(Task.is_active.is_(True)).all()
    due_today = [t for t in candidates if is_task_due_today(t, today)]

    result = []
    for task in due_today:
        period_start, period_end = _period_bounds(task.frequency_type, today, task.frequency_config or {})
        log = (
            db.query(TaskLog)
            .filter(
                TaskLog.task_id == task.id,
                TaskLog.completed_at >= period_start,
                TaskLog.completed_at <= period_end,
            )
            .order_by(TaskLog.completed_at.desc())
            .first()
        )
        if log:
            result.append((task, log))

    result.sort(key=lambda pair: pair[0].frequency_type in FLEXIBLE_TYPES)
    return result


def undo_task_completion(db: Session, log_id: int) -> None:
    """Delete a completion log entry, returning the task to the pending list."""
    log = db.query(TaskLog).filter(TaskLog.id == log_id).first()
    if log:
        db.delete(log)


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
