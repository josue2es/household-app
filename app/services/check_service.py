"""
Check service — the daily quality checks of the housekeeper's work.

How it works:
  1. The first time a housekeeper opens the app each day, tasks scheduled
     for that day are drawn at random (`ensure_daily_checks`):
       - PHOTO_CHECKS_PER_DAY "photo" checks: the housekeeper completes
         these by taking a photo that proves the work was done.
       - INSPECTIONS_PER_DAY "inspection" checks: a manager inspects these
         in person and takes a photo. The housekeeper doesn't know which
         tasks they are until they have been rated.
     Drawing on the housekeeper's first visit means nothing is drawn on
     days she doesn't work, or while no housekeeper account exists.
  2. A manager rates every check from 1 to 5 stars, with an optional
     comment (`review_check`).
  3. The housekeeper reads the ratings and comments (`get_feedback`).

Only tasks with a fixed day (SPECIFIC_DATE_TYPES: daily, weekly, ...) are
drawn: a flexible "any day this month" task might not be planned for today.
"""
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task, TaskCheck
from app.services.photo_service import save_photo, delete_photo
from app.services.task_service import (
    LOCAL_TZ,
    SPECIFIC_DATE_TYPES,
    is_task_due_today,
    complete_task,
    get_completion_on,
)

KIND_PHOTO = "photo"
KIND_INSPECTION = "inspection"

PHOTO_CHECKS_PER_DAY = 2
INSPECTIONS_PER_DAY = 2

# Unrated checks older than this no longer count as pending for the manager.
REVIEW_WINDOW_DAYS = 14

MIN_RATING, MAX_RATING = 1, 5


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


# --- The daily draw ---

def ensure_daily_checks(day: date | None = None) -> None:
    """
    Draw the day's checks if that hasn't happened yet. Safe to call on
    every page load: once a day has checks, it does nothing.

    Unlike the other functions here it opens its own DB session, because
    it must be able to roll back on its own: if another process (e.g. the
    MCP server) draws the same day at the same moment, our insert hits the
    unique constraints on TaskCheck and we simply keep their draw.
    """
    day = day or local_today()
    try:
        with get_db() as db:
            if db.query(TaskCheck.id).filter(TaskCheck.day == day).first():
                return
            for check in _draw(db, day):
                db.add(check)
    except IntegrityError:
        pass  # someone else drew this day first


def _draw(db: Session, day: date) -> list[TaskCheck]:
    candidates = [
        t for t in db.query(Task).filter(Task.is_active.is_(True)).all()
        if t.frequency_type in SPECIFIC_DATE_TYPES and is_task_due_today(t, day)
    ]
    random.shuffle(candidates)

    # A task someone already completed today can't get a "before it's done"
    # photo anymore, but it can still be inspected.
    not_done = [t for t in candidates if get_completion_on(db, t.id, day) is None]
    photo_tasks = not_done[:PHOTO_CHECKS_PER_DAY]
    inspection_tasks = [t for t in candidates if t not in photo_tasks][:INSPECTIONS_PER_DAY]

    return (
        [TaskCheck(day=day, kind=KIND_PHOTO, slot=i, task_id=t.id)
         for i, t in enumerate(photo_tasks, start=1)]
        + [TaskCheck(day=day, kind=KIND_INSPECTION, slot=i, task_id=t.id)
           for i, t in enumerate(inspection_tasks, start=1)]
    )


# --- Reading checks ---

def get_checks(db: Session, day: date, kind: str) -> list[TaskCheck]:
    return (
        db.query(TaskCheck)
        .filter(TaskCheck.day == day, TaskCheck.kind == kind)
        .order_by(TaskCheck.slot)
        .all()
    )


def task_needs_photo(db: Session, task_id: int, day: date) -> bool:
    """True if the task is one of the day's photo checks and has no photo yet."""
    return db.query(TaskCheck.id).filter(
        TaskCheck.day == day,
        TaskCheck.kind == KIND_PHOTO,
        TaskCheck.task_id == task_id,
        TaskCheck.photo_path.is_(None),
    ).first() is not None


def can_review(check: TaskCheck, today: date) -> bool:
    """
    Whether a manager can rate this check now.

    Inspections need the manager's photo first. A photo check can be rated
    once its photo arrives, or from the next day on without one (so the
    manager can say the task wasn't done).
    """
    if check.kind == KIND_INSPECTION:
        return check.photo_path is not None
    return check.photo_path is not None or check.day < today


# --- Photos ---

def submit_photo(check_id: int, user_id: int, image_bytes: bytes) -> None:
    """
    Save a photo for a check: the housekeeper's proof (photo checks) or the
    manager's inspection photo. Opens its own DB sessions.

    Blocking (see photo_service.save_photo): call it via `run.io_bound`.
    """
    with get_db() as db:
        check = db.get(TaskCheck, check_id)
        if check is None:
            raise ValueError("Revisión no encontrada")
        day, kind = check.day, check.kind

    photo_path = save_photo(image_bytes, day, check_id)
    try:
        with get_db() as db:
            if kind == KIND_PHOTO:
                old_path = record_proof_photo(db, check_id, user_id, photo_path)
            else:
                old_path = record_inspection_photo(db, check_id, user_id, photo_path)
    except Exception:
        delete_photo(photo_path)  # not recorded: don't leave the file behind
        raise
    delete_photo(old_path)


def record_proof_photo(db: Session, check_id: int, user_id: int, photo_path: str) -> str | None:
    """
    Attach the housekeeper's proof photo to a photo check and mark the
    task as completed (if it isn't already). Only today's checks accept a
    proof. Returns the replaced photo's path (to delete), if any.
    """
    check = _get_check(db, check_id, KIND_PHOTO)
    if check.day != local_today():
        raise ValueError("Solo se puede enviar la foto el mismo día")
    if check.rating is not None:
        raise ValueError("Esta tarea ya fue evaluada")
    old_path = _set_photo(check, user_id, photo_path)
    if get_completion_on(db, check.task_id, check.day) is None:
        complete_task(db, check.task_id, user_id)
    return old_path


def record_inspection_photo(db: Session, check_id: int, user_id: int, photo_path: str) -> str | None:
    """Attach the manager's inspection photo. Returns the replaced photo's path, if any."""
    check = _get_check(db, check_id, KIND_INSPECTION)
    return _set_photo(check, user_id, photo_path)


def undo_proof(db: Session, check_id: int) -> str | None:
    """
    Take back a proof photo that hasn't been rated yet: the photo is
    removed and the task goes back to pending. Returns the photo's path
    (to delete).
    """
    check = _get_check(db, check_id, KIND_PHOTO)
    if check.rating is not None:
        raise ValueError("Esta tarea ya fue evaluada")
    log = get_completion_on(db, check.task_id, check.day)
    if log is not None:
        db.delete(log)
    old_path = check.photo_path
    check.photo_path = None
    check.photo_by_user_id = None
    check.photo_at = None
    return old_path


def _set_photo(check: TaskCheck, user_id: int, photo_path: str) -> str | None:
    old_path = check.photo_path
    check.photo_path = photo_path
    check.photo_by_user_id = user_id
    check.photo_at = datetime.utcnow()
    return old_path


def _get_check(db: Session, check_id: int, kind: str) -> TaskCheck:
    check = db.get(TaskCheck, check_id)
    if check is None or check.kind != kind:
        raise ValueError("Revisión no encontrada")
    return check


# --- Reviews ---

def review_check(db: Session, check_id: int, reviewer_id: int, rating: int, comment: str) -> None:
    """Save (or replace) a manager's rating and comment."""
    check = db.get(TaskCheck, check_id)
    if check is None:
        raise ValueError("Revisión no encontrada")
    if not can_review(check, local_today()):
        raise ValueError("Primero se necesita la foto")
    if not (rating and MIN_RATING <= int(rating) <= MAX_RATING):
        raise ValueError(f"Elige de {MIN_RATING} a {MAX_RATING} estrellas")
    check.rating = int(rating)
    check.comment = (comment or "").strip()
    check.reviewed_by_user_id = reviewer_id
    check.reviewed_at = datetime.utcnow()
    check.seen_at = None  # new or edited: the housekeeper should read it


def _pending_filter(today: date):
    """SQL condition for checks that wait on a manager (see pending_review_*)."""
    return (
        (TaskCheck.day >= today - timedelta(days=REVIEW_WINDOW_DAYS))
        & TaskCheck.rating.is_(None)
        & (
            # Today's inspections, still to be done.
            ((TaskCheck.kind == KIND_INSPECTION) & (TaskCheck.day == today))
            # Inspections from earlier days that were photographed but not rated.
            | ((TaskCheck.kind == KIND_INSPECTION) & TaskCheck.photo_path.isnot(None))
            # Photo checks with a photo, or from earlier days (photo or not).
            | ((TaskCheck.kind == KIND_PHOTO)
               & (TaskCheck.photo_path.isnot(None) | (TaskCheck.day < today)))
        )
    )


def pending_review_count(db: Session, today: date) -> int:
    """How many checks wait on a manager: shown as a badge on 'Revisión'."""
    return db.query(func.count(TaskCheck.id)).filter(_pending_filter(today)).scalar()


def pending_review_days(db: Session, today: date) -> list[date]:
    """Earlier days that still have checks waiting on a manager, oldest first."""
    rows = (
        db.query(TaskCheck.day)
        .filter(_pending_filter(today), TaskCheck.day < today)
        .distinct()
        .order_by(TaskCheck.day)
        .all()
    )
    return [row[0] for row in rows]


def average_rating(db: Session, since: date) -> tuple[float | None, int]:
    """(average stars, number of ratings) for checks since a day."""
    avg, count = (
        db.query(func.avg(TaskCheck.rating), func.count(TaskCheck.rating))
        .filter(TaskCheck.day >= since, TaskCheck.rating.isnot(None))
        .one()
    )
    return (float(avg) if avg is not None else None), count


# --- The housekeeper's feedback ---

def get_feedback(db: Session, since: date) -> list[TaskCheck]:
    """Rated checks (both kinds) since a day, most recently rated first."""
    return (
        db.query(TaskCheck)
        .filter(TaskCheck.day >= since, TaskCheck.rating.isnot(None))
        .order_by(TaskCheck.reviewed_at.desc())
        .all()
    )


def unseen_feedback_count(db: Session) -> int:
    """Ratings the housekeeper hasn't opened yet: shown as a badge on 'Evaluaciones'."""
    return db.query(func.count(TaskCheck.id)).filter(
        TaskCheck.rating.isnot(None), TaskCheck.seen_at.is_(None)
    ).scalar()


def mark_feedback_seen(db: Session, check_ids: list[int]) -> None:
    if check_ids:
        db.query(TaskCheck).filter(
            TaskCheck.id.in_(check_ids), TaskCheck.seen_at.is_(None)
        ).update({TaskCheck.seen_at: datetime.utcnow()}, synchronize_session=False)
