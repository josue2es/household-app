"""
Household admin CLI tool.

Usage:
    python -m app.admin              # Interactive menu
    python -m app.admin --update     # Same, but CSV imports overwrite duplicates

Run inside the container:
    docker compose exec household-app python -m app.admin
"""
import sys
import csv
from datetime import date
from getpass import getpass
from pathlib import Path
from app.database import get_db
from app.models import User, GroceryItem, Task


# Parse command-line flags once at startup.
# argparse would be overkill for one flag — sys.argv is fine.
UPDATE_MODE = "--update" in sys.argv


# ============================================================
# UI helpers
# ============================================================

def print_header(title: str) -> None:
    """Render a header bar so menus visually separate from output."""
    print()
    print("=" * 50)
    print(f"  {title}")
    print("=" * 50)


def prompt(message: str) -> str:
    """
    Read input with a consistent prompt style.
    Strips whitespace so 'Alice ' and 'Alice' are the same.
    """
    return input(f"{message}: ").strip()


def pause() -> None:
    """Wait for the user to acknowledge a result before redrawing the menu."""
    input("\nPress Enter to continue...")


# ============================================================
# Main menu
# ============================================================

def main_menu() -> None:
    """Top-level menu loop. Returns when the user picks 0."""
    while True:
        print_header("Household Admin")
        if UPDATE_MODE:
            print("  [Update mode: CSV imports will overwrite existing items]")
        print()
        print("  1. Manage users")
        print("  2. List all groceries")
        print("  3. List all tasks")
        print("  4. Import grocery items from CSV")
        print("  5. Import tasks from CSV")
        print("  6. Export current data to CSV")
        print("  0. Exit")
        print()

        choice = prompt("Choose an option")

        if choice == "1":
            users_menu()
        elif choice == "2":
            list_groceries()
            pause()
        elif choice == "3":
            list_tasks()
            pause()
        elif choice == "4":
            import_groceries()
            pause()
        elif choice == "5":
            import_tasks()
            pause()
        elif choice == "6":
            export_data()
            pause()
        elif choice == "0":
            print("\nGoodbye!")
            return
        else:
            print(f"\nInvalid choice: '{choice}'")
            pause()

# ============================================================
# List views
# ============================================================

WEEKDAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _format_frequency(ftype: str, config: dict) -> str:
    """Return a compact human-readable frequency string for table display."""
    if ftype == "daily":
        return "Diario"
    if ftype == "once":
        return f"Una vez ({config.get('date', '?')})"
    if ftype == "weekly":
        day = config.get("weekday", "?")
        name = WEEKDAY_NAMES[day] if isinstance(day, int) and 0 <= day <= 6 else str(day)
        return f"Semanal ({name})"
    if ftype == "specific_days":
        days = config.get("weekdays", [])
        names = ", ".join(WEEKDAY_NAMES[d] for d in days if 0 <= d <= 6)
        return f"Días específicos ({names})"
    if ftype == "monthly":
        return f"Mensual (día {config.get('day', '?')})"
    if ftype == "weekly_any":
        return "Semanal (libre)"
    if ftype == "monthly_any":
        return "Mensual (libre)"
    if ftype == "bimonthly_any":
        return "Bimestral (libre)"
    if ftype == "every_x_days":
        return f"Cada {config.get('days', '?')} días"
    return ftype


def list_groceries() -> None:
    """Print a table of all grocery items sorted by category then name."""
    with get_db() as db:
        items = (
            db.query(GroceryItem)
            .order_by(GroceryItem.category, GroceryItem.name)
            .all()
        )
        rows = [(i.id, i.name, i.category, i.purchase_count) for i in items]

    if not rows:
        print("\n(No grocery items found)")
        return

    print()
    print(f"  {'ID':<4} {'Nombre':<28} {'Categoría':<22} {'Compras':>7}")
    print(f"  {'-'*4} {'-'*28} {'-'*22} {'-'*7}")
    for iid, name, category, count in rows:
        print(f"  {iid:<4} {name:<28} {category:<22} {count:>7}")
    print(f"\n  {len(rows)} artículo(s) en total")


def list_tasks() -> None:
    """Print a table of all active tasks."""
    with get_db() as db:
        tasks = (
            db.query(Task)
            .filter(Task.is_active.is_(True))
            .order_by(Task.name)
            .all()
        )
        rows = [
            (t.id, t.name, _format_frequency(t.frequency_type, t.frequency_config or {}), t.description or "")
            for t in tasks
        ]

    if not rows:
        print("\n(No tasks found)")
        return

    print()
    print(f"  {'ID':<4} {'Nombre':<28} {'Frecuencia':<28} {'Descripción'}")
    print(f"  {'-'*4} {'-'*28} {'-'*28} {'-'*24}")
    for tid, name, freq, desc in rows:
        short_desc = desc[:40] + "…" if len(desc) > 40 else desc
        print(f"  {tid:<4} {name:<28} {freq:<28} {short_desc}")
    print(f"\n  {len(rows)} tarea(s) en total")


# ============================================================
# Users submenu
# ============================================================

def users_menu() -> None:
    """Submenu for user management. Returns to main menu when user picks 0."""
    while True:
        print_header("User Management")
        print("  1. List all users")
        print("  2. Create new user")
        print("  3. Change user password")
        print("  4. Edit user (name / color)")
        print("  5. Delete user")
        print("  0. Back to main menu")
        print()

        choice = prompt("Choose an option")

        if choice == "1":
            list_users()
            pause()
        elif choice == "2":
            create_user()
            pause()
        elif choice == "3":
            change_user_password()
            pause()
        elif choice == "4":
            edit_user()
            pause()
        elif choice == "5":
            delete_user()
            pause()
        elif choice == "0":
            return
        else:
            print(f"\nInvalid choice: '{choice}'")
            pause()

# ============================================================
# User operations
# ============================================================

# Quasar avatar colors that look reasonable
AVATAR_COLORS = ["red", "pink", "purple", "deep-purple", "indigo", "blue",
                 "light-blue", "cyan", "teal", "green", "amber", "orange"]


def list_users() -> None:
    """Print a table of all users."""
    with get_db() as db:
        users = db.query(User).order_by(User.name).all()
        if not users:
            print("\n(No users found)")
            return
        # Detach what we need before session closes
        rows = [(u.id, u.name, u.avatar_color, u.created_at) for u in users]

    print()
    print(f"  {'ID':<4} {'Name':<20} {'Color':<14} {'Created'}")
    print(f"  {'-'*4} {'-'*20} {'-'*14} {'-'*19}")
    for uid, name, color, created in rows:
        created_str = created.strftime("%Y-%m-%d %H:%M") if created else "?"
        print(f"  {uid:<4} {name:<20} {color:<14} {created_str}")
    print(f"\n  {len(rows)} user(s) total")


def create_user() -> None:
    """Interactively create a new user."""
    print()
    name = prompt("New user name")
    if not name:
        print("Cancelled (empty name).")
        return

    # Check uniqueness
    with get_db() as db:
        existing = db.query(User).filter(User.name == name).first()
        if existing:
            print(f"User '{name}' already exists.")
            return

    color = pick_color()
    if color is None:
        return  # user cancelled

    password = pick_password()
    if password is None:
        return

    with get_db() as db:
        user = User(name=name, avatar_color=color)
        user.set_password(password)
        db.add(user)
        # commit happens automatically when the with-block exits successfully

    print(f"\n✓ User '{name}' created successfully.")


def change_user_password() -> None:
    """Change a user's password without affecting any other field."""
    user = pick_user("Change password for which user?")
    if user is None:
        return

    password = pick_password()
    if password is None:
        return

    # Re-query inside this session and update — don't reuse the detached object
    with get_db() as db:
        u = db.query(User).filter(User.id == user["id"]).first()
        u.set_password(password)

    print(f"\n✓ Password updated for '{user['name']}'.")


def edit_user() -> None:
    """Edit a user's name or avatar color."""
    user = pick_user("Edit which user?")
    if user is None:
        return

    print(f"\nCurrent: name='{user['name']}', color='{user['color']}'")
    print("(Press Enter to keep the current value)\n")

    new_name = prompt(f"New name [{user['name']}]") or user["name"]
    new_color = pick_color(default=user["color"])
    if new_color is None:
        return

    # Check name conflict (only if name changed)
    if new_name != user["name"]:
        with get_db() as db:
            conflict = db.query(User).filter(User.name == new_name).first()
            if conflict:
                print(f"\nName '{new_name}' already taken.")
                return

    with get_db() as db:
        u = db.query(User).filter(User.id == user["id"]).first()
        u.name = new_name
        u.avatar_color = new_color

    print(f"\n✓ User updated.")


def delete_user() -> None:
    """Delete a user. Asks for explicit confirmation."""
    user = pick_user("Delete which user?")
    if user is None:
        return

    print(f"\n⚠ This will delete '{user['name']}' permanently.")
    print("  Their task completion history and grocery additions will become orphan records.")
    confirm = prompt(f"Type the username '{user['name']}' to confirm")
    if confirm != user["name"]:
        print("Cancelled.")
        return

    with get_db() as db:
        u = db.query(User).filter(User.id == user["id"]).first()
        if u:
            db.delete(u)

    print(f"\n✓ User '{user['name']}' deleted.")


# ============================================================
# Small helpers used by the user operations
# ============================================================

def pick_user(message: str) -> dict | None:
    """
    Show a numbered list of users, prompt for selection.
    Returns a dict with id/name/color, or None if cancelled.
    """
    with get_db() as db:
        users = db.query(User).order_by(User.name).all()
        rows = [(u.id, u.name, u.avatar_color) for u in users]

    if not rows:
        print("\n(No users to choose from)")
        return None

    print()
    for idx, (uid, name, color) in enumerate(rows, start=1):
        print(f"  {idx}. {name} ({color})")
    print(f"  0. Cancel")
    print()

    choice = prompt(message)
    if choice == "0" or choice == "":
        return None
    try:
        idx = int(choice)
        if not 1 <= idx <= len(rows):
            raise ValueError
    except ValueError:
        print(f"Invalid selection: '{choice}'")
        return None

    uid, name, color = rows[idx - 1]
    return {"id": uid, "name": name, "color": color}


def pick_color(default: str | None = None) -> str | None:
    """Show a numbered list of colors. Returns the chosen color name or None on cancel."""
    print("\n  Available colors:")
    for idx, c in enumerate(AVATAR_COLORS, start=1):
        marker = "  ← current" if c == default else ""
        print(f"  {idx:>2}. {c}{marker}")
    print()

    label = "Pick a color"
    if default:
        label += f" [Enter to keep '{default}']"
    choice = prompt(label)

    if choice == "" and default:
        return default
    try:
        idx = int(choice)
        if not 1 <= idx <= len(AVATAR_COLORS):
            raise ValueError
        return AVATAR_COLORS[idx - 1]
    except ValueError:
        print(f"Invalid color choice: '{choice}'")
        return None

def pick_password() -> str | None:
    """Prompt twice for a password. Returns the password or None on cancel/mismatch."""
    pw1 = getpass("New password (hidden, min 6 chars): ")
    if not pw1:
        print("Cancelled (empty password).")
        return None
    if len(pw1) < 6:
        print("Password too short (min 6 chars).")
        return None

    pw2 = getpass("Repeat password: ")
    if pw1 != pw2:
        print("Passwords don't match.")
        return None

    return pw1
# ============================================================
# CSV Imports
# ============================================================

VALID_CATEGORIES = {
    "Despensa",
    "Frescos",
    "Carnes y Lácteos",
    "Panadería",
    "Cuidado Personal",
    "Limpieza del Hogar",
    "Mascotas",
    "Otros",
}


def import_groceries() -> None:
    """Bulk-import grocery items from a CSV file."""
    print_header("Import Grocery Items")
    print("\nExpected CSV columns: name, category, purchase_count")
    print(f"Categories: {', '.join(sorted(VALID_CATEGORIES))}")
    print("\nExample row:  Café,Despensa,15\n")

    path_str = prompt("Path to CSV file")
    if not path_str:
        print("Cancelled.")
        return

    path = Path(path_str).expanduser()
    if not path.is_file():
        print(f"File not found: {path}")
        return

    # Read all rows first so we can show counts before committing anything.
    rows = _read_grocery_csv(path)
    if rows is None:
        return  # error already reported
    if not rows:
        print("CSV is empty (no data rows).")
        return

    print(f"\nFound {len(rows)} row(s). Importing...")
    if UPDATE_MODE:
        print("[Update mode: existing items will be overwritten]\n")
    else:
        print("[Skip mode: existing items will be left alone]\n")

    stats = _apply_grocery_rows(rows)

    print()
    print(f"  Created:    {stats['created']}")
    print(f"  Updated:    {stats['updated']}")
    print(f"  Skipped:    {stats['skipped']}")
    print(f"  Row errors: {stats['errors']}")


def _read_grocery_csv(path: Path) -> list[dict] | None:
    """
    Read and validate the CSV. Returns a list of cleaned dicts,
    or None if the file structure is invalid.

    Why split read from apply? So we can fail early on bad files
    without partially writing to the DB.
    """
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            required = {"name", "category", "purchase_count"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                print(f"Missing required columns: {', '.join(sorted(missing))}")
                return None

            rows: list[dict] = []
            for line_num, raw in enumerate(reader, start=2):  # line 1 is header
                cleaned = _clean_grocery_row(raw, line_num)
                if cleaned is not None:
                    rows.append(cleaned)
            return rows
    except OSError as e:
        print(f"Could not read file: {e}")
        return None


def _clean_grocery_row(raw: dict, line_num: int) -> dict | None:
    """
    Validate one CSV row. Returns a cleaned dict or None if invalid.
    Bad rows are reported but don't stop the whole import.
    """
    name = (raw.get("name") or "").strip()
    category = (raw.get("category") or "").strip()
    count_str = (raw.get("purchase_count") or "0").strip()

    if not name:
        print(f"  Line {line_num}: skipped — name is empty")
        return None

    if category not in VALID_CATEGORIES:
        print(f"  Line {line_num}: skipped — invalid category '{category}'")
        return None

    try:
        count = int(count_str) if count_str else 0
        if count < 0:
            raise ValueError("negative")
    except ValueError:
        print(f"  Line {line_num}: skipped — invalid purchase_count '{count_str}'")
        return None

    return {"name": name, "category": category, "purchase_count": count}


def _apply_grocery_rows(rows: list[dict]) -> dict:
    """Insert/update each row. Returns counts of what happened."""
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    with get_db() as db:
        # Pre-fetch existing items into a lookup map (case-insensitive)
        existing = {
            item.name.lower(): item
            for item in db.query(GroceryItem).all()
        }

        for row in rows:
            try:
                key = row["name"].lower()
                if key in existing:
                    if UPDATE_MODE:
                        item = existing[key]
                        item.category = row["category"]
                        item.purchase_count = row["purchase_count"]
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    db.add(GroceryItem(
                        name=row["name"],
                        category=row["category"],
                        purchase_count=row["purchase_count"],
                    ))
                    stats["created"] += 1
            except Exception as e:
                print(f"  Error on row '{row.get('name', '?')}': {e}")
                stats["errors"] += 1

    return stats

# ============================================================
# Task CSV Import
# ============================================================

VALID_FREQUENCIES = {
    "once", "daily", "weekly", "specific_days", "monthly",
    "weekly_any", "monthly_any", "bimonthly_any", "every_x_days",
}


def import_tasks() -> None:
    """Bulk-import tasks from a CSV file."""
    print_header("Import Tasks")
    print("\nExpected CSV columns: name, description, frequency_type, frequency_value")
    print("\nfrequency_value depends on frequency_type:")
    print("  daily          (leave empty)")
    print("  weekly         weekday number 0-6 (0=Mon, 6=Sun)")
    print("  monthly        day of month 1-31")
    print("  specific_days  comma-separated weekdays, e.g. 1,4")
    print("  once           date in YYYY-MM-DD format")
    print("  weekly_any     (leave empty) — once per week, any day")
    print("  monthly_any    (leave empty) — once per month, any day")
    print("  bimonthly_any  (leave empty) — once per two-month block, any day")
    print("  every_x_days   number of days — reappears X days after last completion")
    print("\nExample row:  Sacar la basura,Martes y viernes,specific_days,\"1,4\"\n")

    path_str = prompt("Path to CSV file")
    if not path_str:
        print("Cancelled.")
        return

    path = Path(path_str).expanduser()
    if not path.is_file():
        print(f"File not found: {path}")
        return

    rows = _read_task_csv(path)
    if rows is None:
        return
    if not rows:
        print("CSV is empty (no valid data rows).")
        return

    print(f"\nFound {len(rows)} valid row(s). Importing...")
    if UPDATE_MODE:
        print("[Update mode: tasks with matching name will be overwritten]\n")
    else:
        print("[Skip mode: tasks with matching name will be left alone]\n")

    stats = _apply_task_rows(rows)

    print()
    print(f"  Created:    {stats['created']}")
    print(f"  Updated:    {stats['updated']}")
    print(f"  Skipped:    {stats['skipped']}")
    print(f"  Row errors: {stats['errors']}")


def _read_task_csv(path: Path) -> list[dict] | None:
    """Read and validate task CSV. Returns cleaned rows or None on file error."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            required = {"name", "description", "frequency_type", "frequency_value"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                print(f"Missing required columns: {', '.join(sorted(missing))}")
                return None

            rows: list[dict] = []
            for line_num, raw in enumerate(reader, start=2):
                cleaned = _clean_task_row(raw, line_num)
                if cleaned is not None:
                    rows.append(cleaned)
            return rows
    except OSError as e:
        print(f"Could not read file: {e}")
        return None


def _clean_task_row(raw: dict, line_num: int) -> dict | None:
    """Validate one task row. Returns cleaned dict or None on error."""
    name = (raw.get("name") or "").strip()
    description = (raw.get("description") or "").strip()
    ftype = (raw.get("frequency_type") or "").strip().lower()
    fvalue = (raw.get("frequency_value") or "").strip()

    if not name:
        print(f"  Line {line_num}: skipped — name is empty")
        return None

    if ftype not in VALID_FREQUENCIES:
        print(f"  Line {line_num}: skipped — invalid frequency_type '{ftype}'")
        return None

    # Parse frequency_value into a JSON config dict, depending on type.
    config = _parse_frequency_value(ftype, fvalue, line_num)
    no_value_types = {"daily", "weekly_any", "monthly_any", "bimonthly_any"}
    if config is None and ftype not in no_value_types:
        # Types with no value use an empty config — None means a parse error for the rest
        return None

    return {
        "name": name,
        "description": description,
        "frequency_type": ftype,
        "frequency_config": config or {},
    }


def _parse_frequency_value(ftype: str, fvalue: str, line_num: int) -> dict | None:
    """
    Convert the raw frequency_value string into the JSON config dict the model expects.

    Returns:
        - dict on success
        - {} if ftype is daily (no value needed)
        - None on parse error (caller treats this as "skip row")
    """
    if ftype in ("daily", "weekly_any", "monthly_any", "bimonthly_any"):
        return {}

    if ftype == "every_x_days":
        try:
            days = int(fvalue)
            if days < 1:
                raise ValueError
        except ValueError:
            print(f"  Line {line_num}: skipped — every_x_days needs a positive integer, got '{fvalue}'")
            return None
        return {"days": days}

    if ftype == "weekly":
        try:
            weekday = int(fvalue)
            if not 0 <= weekday <= 6:
                raise ValueError
        except ValueError:
            print(f"  Line {line_num}: skipped — weekly needs weekday 0-6, got '{fvalue}'")
            return None
        return {"weekday": weekday}

    if ftype == "monthly":
        try:
            day = int(fvalue)
            if not 1 <= day <= 31:
                raise ValueError
        except ValueError:
            print(f"  Line {line_num}: skipped — monthly needs day 1-31, got '{fvalue}'")
            return None
        return {"day": day}

    if ftype == "specific_days":
        try:
            parts = [int(p.strip()) for p in fvalue.split(",") if p.strip()]
            if not parts or any(p < 0 or p > 6 for p in parts):
                raise ValueError
        except ValueError:
            print(f"  Line {line_num}: skipped — specific_days needs '1,4' style 0-6, got '{fvalue}'")
            return None
        return {"weekdays": sorted(set(parts))}

    if ftype == "once":
        try:
            parsed = date.fromisoformat(fvalue)
        except ValueError:
            print(f"  Line {line_num}: skipped — once needs YYYY-MM-DD, got '{fvalue}'")
            return None
        return {"date": parsed.isoformat()}

    return None  # unreachable but keeps the type checker happy


def _apply_task_rows(rows: list[dict]) -> dict:
    """Insert/update tasks in DB. Returns stats."""
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    with get_db() as db:
        # Pre-fetch existing tasks (case-insensitive name lookup, only active ones)
        existing = {
            t.name.lower(): t
            for t in db.query(Task).filter(Task.is_active.is_(True)).all()
        }

        for row in rows:
            try:
                key = row["name"].lower()
                if key in existing:
                    if UPDATE_MODE:
                        t = existing[key]
                        t.description = row["description"]
                        t.frequency_type = row["frequency_type"]
                        t.frequency_config = row["frequency_config"]
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    db.add(Task(
                        name=row["name"],
                        description=row["description"],
                        frequency_type=row["frequency_type"],
                        frequency_config=row["frequency_config"],
                        is_active=True,
                    ))
                    stats["created"] += 1
            except Exception as e:
                print(f"  Error on row '{row.get('name', '?')}': {e}")
                stats["errors"] += 1

    return stats

# ============================================================
# CSV Export
# ============================================================

from datetime import datetime  # add this near the other datetime imports if not already there


def export_data() -> None:
    """Export users, groceries, and tasks to a timestamped folder of CSVs."""
    print_header("Export Data")

    default_dir = Path("./exports")
    print(f"\nExports go to a timestamped subfolder under: {default_dir.resolve()}")
    print("(Press Enter to use the default, or type a different base path)\n")

    base_str = prompt(f"Base folder [./exports]") or str(default_dir)
    base = Path(base_str).expanduser()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = base / f"household_export_{timestamp}"

    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Could not create folder: {e}")
        return

    print(f"\nExporting to: {target.resolve()}\n")

    user_count = _export_users(target / "users.csv")
    grocery_count = _export_groceries(target / "groceries.csv")
    task_count = _export_tasks(target / "tasks.csv")

    print(f"  users.csv:     {user_count} row(s)")
    print(f"  groceries.csv: {grocery_count} row(s)")
    print(f"  tasks.csv:     {task_count} row(s)")
    print(f"\n✓ Done. Files saved to {target.resolve()}")


def _export_users(path: Path) -> int:
    """
    Write users.csv. Note: we do NOT export password_hash.
    Re-importing users would need a separate flow (or set placeholder passwords).
    """
    with get_db() as db:
        rows = [
            (u.name, u.avatar_color, u.created_at.isoformat() if u.created_at else "")
            for u in db.query(User).order_by(User.name).all()
        ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "avatar_color", "created_at"])
        writer.writerows(rows)
    return len(rows)


def _export_groceries(path: Path) -> int:
    """Write groceries.csv in the same format the importer reads."""
    with get_db() as db:
        rows = [
            (item.name, item.category, item.purchase_count)
            for item in db.query(GroceryItem).order_by(GroceryItem.name).all()
        ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "category", "purchase_count"])
        writer.writerows(rows)
    return len(rows)


def _export_tasks(path: Path) -> int:
    """
    Write tasks.csv in the same format the importer reads.
    Only exports active tasks (soft-deleted ones are skipped).
    """
    with get_db() as db:
        tasks = db.query(Task).filter(Task.is_active.is_(True)).order_by(Task.name).all()
        rows = []
        for t in tasks:
            fvalue = _frequency_config_to_value(t.frequency_type, t.frequency_config or {})
            rows.append((t.name, t.description, t.frequency_type, fvalue))

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "description", "frequency_type", "frequency_value"])
        writer.writerows(rows)
    return len(rows)


def _frequency_config_to_value(ftype: str, config: dict) -> str:
    """
    Inverse of _parse_frequency_value: turn the JSON config back into the CSV value string.
    Matches the format the import expects so round-trip works.
    """
    if ftype in ("daily", "weekly_any", "monthly_any", "bimonthly_any"):
        return ""
    if ftype == "weekly":
        return str(config.get("weekday", ""))
    if ftype == "monthly":
        return str(config.get("day", ""))
    if ftype == "specific_days":
        days = config.get("weekdays", [])
        return ",".join(str(d) for d in days)
    if ftype == "once":
        return config.get("date", "")
    if ftype == "every_x_days":
        return str(config.get("days", ""))
    return ""

# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Bye!")
        sys.exit(0)