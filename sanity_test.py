"""
Quick sanity test — run this to verify the DB layer works.

Usage:
    python -m sanity_test
"""
from datetime import date
from app.database import get_db
from app.models import User, Task
from app.services.task_service import is_task_due_today, get_pending_tasks_today
from app.services.grocery_service import search_suggestions


def main():
    with get_db() as db:
        print("=== USERS ===")
        for u in db.query(User).all():
            ok = u.check_password("alice123") if u.name == "Alice" else False
            print(f"  {u.name} (color={u.avatar_color}, alice123 valid? {ok})")

        print("\n=== TASKS DUE TODAY ===")
        pending = get_pending_tasks_today(db)
        if not pending:
            print("  (none)")
        for t in pending:
            print(f"  • {t.name} [{t.frequency_type}]")

        print("\n=== ALL TASKS — DUE TODAY? ===")
        for t in db.query(Task).all():
            print(f"  {t.name:25s} due today? {is_task_due_today(t)}")

        print("\n=== TOP 5 GROCERY SUGGESTIONS ===")
        for item in search_suggestions(db, query="", limit=5):
            print(f"  {item.name:15s} {item.category:20s} bought {item.purchase_count}x")

        print("\n=== SEARCH 'co' ===")
        for item in search_suggestions(db, query="co", limit=5):
            print(f"  {item.name}")

    print("\n✅ Sanity check passed!")


if __name__ == "__main__":
    main()