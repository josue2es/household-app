"""
Household App MCP Server.

Exposes task and grocery tools so AI agents can read and update the
app without going through the web UI.

Run locally:
    python -m app.mcp_server

The server uses stdio transport by default, which is what MCP clients
(Claude Desktop, Claude Code, etc.) expect when they launch it as a
subprocess.
"""
import sys
from pathlib import Path

# When launched by `mcp dev` or a client subprocess, the project root
# may not be on sys.path. This ensures `app.*` imports always resolve.
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, datetime, timezone
from mcp.server.fastmcp import FastMCP

from app.database import get_db
from app.models import User, Task
from app.services.task_service import (
    LOCAL_TZ,
    get_pending_tasks_today,
    get_completed_tasks_for_today,
    complete_task as svc_complete_task,
    remove_task as svc_remove_task,
    create_task as svc_create_task,
)
from app.services.grocery_service import (
    get_active_list,
    add_to_active_list,
    mark_as_purchased,
    remove_from_active_list,
)

mcp = FastMCP("household-app")


# ============================================================
# Internal helpers (not tools — never called by the AI directly)
# ============================================================

def _resolve_user(user_name: str) -> tuple[int, str | None]:
    """
    Look up a user by name.
    Returns (user_id, None) on success or (0, error_message) on failure.
    """
    with get_db() as db:
        user = db.query(User).filter(User.name == user_name).first()
        if not user:
            return 0, f"User '{user_name}' not found. Check the name and try again."
        return user.id, None


def _parse_freq_config(ftype: str, fvalue: str) -> tuple[dict, str | None]:
    """
    Convert a frequency_value string into the JSON config dict the Task model stores.
    Returns (config_dict, None) on success or ({}, error_message) on failure.
    """
    no_value_types = {"daily", "weekly_any", "monthly_any", "bimonthly_any"}
    if ftype in no_value_types:
        return {}, None

    if ftype == "every_x_days":
        try:
            days = int(fvalue)
            if days < 1:
                raise ValueError
        except ValueError:
            return {}, f"every_x_days requires a positive integer for frequency_value, got '{fvalue}'."
        return {"days": days}, None

    if ftype == "weekly":
        try:
            wd = int(fvalue)
            if not 0 <= wd <= 6:
                raise ValueError
        except ValueError:
            return {}, f"weekly requires a weekday 0–6 (0=Mon, 6=Sun), got '{fvalue}'."
        return {"weekday": wd}, None

    if ftype == "specific_days":
        try:
            parts = [int(p.strip()) for p in fvalue.split(",") if p.strip()]
            if not parts or any(p < 0 or p > 6 for p in parts):
                raise ValueError
        except ValueError:
            return {}, f"specific_days requires comma-separated weekdays 0–6, got '{fvalue}'."
        return {"weekdays": sorted(set(parts))}, None

    if ftype == "monthly":
        try:
            day = int(fvalue)
            if not 1 <= day <= 31:
                raise ValueError
        except ValueError:
            return {}, f"monthly requires a day of month 1–31, got '{fvalue}'."
        return {"day": day}, None

    if ftype == "once":
        try:
            parsed = date.fromisoformat(fvalue)
        except ValueError:
            return {}, f"once requires a date in YYYY-MM-DD format, got '{fvalue}'."
        return {"date": parsed.isoformat()}, None

    return {}, f"Unknown frequency_type '{ftype}'."


def _format_freq(ftype: str, config: dict) -> str:
    labels = {
        "daily": "Diario",
        "weekly_any": "Semanal (cualquier día)",
        "monthly_any": "Mensual (cualquier día)",
        "bimonthly_any": "Bimestral (cualquier día)",
    }
    if ftype in labels:
        return labels[ftype]
    if ftype == "every_x_days":
        return f"Cada {config.get('days', '?')} días"
    if ftype == "weekly":
        days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        wd = config.get("weekday", 0)
        return f"Semanal ({days[wd]})"
    if ftype == "specific_days":
        days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        names = ", ".join(days[d] for d in config.get("weekdays", []))
        return f"Días específicos ({names})"
    if ftype == "monthly":
        return f"Mensual (día {config.get('day', '?')})"
    if ftype == "once":
        return f"Una vez ({config.get('date', '?')})"
    return ftype


# ============================================================
# Task tools
# ============================================================

@mcp.tool()
def list_pending_tasks() -> list[dict]:
    """
    Return all tasks that are pending for today.
    Includes both scheduled tasks (specific day/date) and flexible tasks
    (weekly_any, monthly_any, bimonthly_any, every_x_days).
    Each item includes: id, name, description, frequency, frequency_type.
    """
    with get_db() as db:
        tasks = get_pending_tasks_today(db)
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description or "",
                "frequency": _format_freq(t.frequency_type, t.frequency_config or {}),
                "frequency_type": t.frequency_type,
            }
            for t in tasks
        ]


@mcp.tool()
def list_completed_tasks() -> list[dict]:
    """
    Return all tasks that have been completed today (within their active period).
    Each item includes: id, name, frequency, completed_by, completed_at (local time HH:MM).
    """
    with get_db() as db:
        pairs = get_completed_tasks_for_today(db)
        result = []
        for task, log in pairs:
            local_time = log.completed_at.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
            result.append({
                "id": task.id,
                "name": task.name,
                "frequency": _format_freq(task.frequency_type, task.frequency_config or {}),
                "completed_by": log.user.name,
                "completed_at": local_time.strftime("%H:%M"),
            })
        return result


@mcp.tool()
def complete_task(task_id: int, user_name: str) -> str:
    """
    Mark a task as completed and record who did it.

    Args:
        task_id:   The id of the task to complete (use list_pending_tasks to find it).
        user_name: The name of the user completing the task (must exist in the app).
    """
    user_id, err = _resolve_user(user_name)
    if err:
        return err

    with get_db() as db:
        task = db.query(Task).filter(Task.id == task_id, Task.is_active.is_(True)).first()
        if not task:
            return f"Task with id {task_id} not found or is inactive."
        svc_complete_task(db, task_id, user_id)
        db.commit()
        return f"✓ '{task.name}' marked as completed by {user_name}."


@mcp.tool()
def add_task(
    name: str,
    frequency_type: str,
    frequency_value: str = "",
    description: str = "",
) -> str:
    """
    Create a new household task.

    Args:
        name:            Task name.
        frequency_type:  One of: daily, weekly, specific_days, monthly, once,
                         weekly_any, monthly_any, bimonthly_any, every_x_days.
        frequency_value: Depends on frequency_type:
                           daily / weekly_any / monthly_any / bimonthly_any → leave empty
                           weekly        → weekday number 0–6 (0=Mon, 6=Sun)
                           specific_days → comma-separated weekdays, e.g. "1,4"
                           monthly       → day of month, e.g. "1"
                           once          → date as YYYY-MM-DD
                           every_x_days  → number of days, e.g. "14"
        description:     Optional description shown below the task name.
    """
    config, err = _parse_freq_config(frequency_type, frequency_value)
    if err:
        return err

    with get_db() as db:
        task = svc_create_task(db, name, description, frequency_type, config)
        db.commit()
        return f"✓ Task '{task.name}' created ({_format_freq(frequency_type, config)})."


@mcp.tool()
def delete_task(task_id: int) -> str:
    """
    Deactivate a task so it no longer appears on the dashboard.
    The task's completion history is preserved in the database.

    Args:
        task_id: The id of the task to delete (use list_pending_tasks to find it).
    """
    with get_db() as db:
        task = db.query(Task).filter(Task.id == task_id, Task.is_active.is_(True)).first()
        if not task:
            return f"Task with id {task_id} not found or already inactive."
        name = task.name
        svc_remove_task(db, task_id)
        db.commit()
        return f"✓ Task '{name}' deactivated."


# ============================================================
# Grocery tools
# ============================================================

@mcp.tool()
def get_shopping_list() -> list[dict]:
    """
    Return all items currently on the shopping list (not yet purchased).
    Each item includes: entry_id, name, category, added_by.
    Use entry_id with mark_item_purchased or remove_from_shopping_list.
    """
    with get_db() as db:
        entries = get_active_list(db)
        return [
            {
                "entry_id": e.id,
                "name": e.item.name,
                "category": e.item.category,
                "added_by": e.added_by.name,
            }
            for e in entries
        ]


@mcp.tool()
def add_to_shopping_list(item_name: str, user_name: str) -> str:
    """
    Add an item to the shopping list.
    If the item already exists in the catalog, it is added directly.
    If it is a brand-new item, it is saved to the catalog under category 'Otros'.
    Use the web UI to assign the correct category to new items afterward.

    Args:
        item_name: Name of the grocery item to add.
        user_name: Name of the user adding the item (must exist in the app).
    """
    user_id, err = _resolve_user(user_name)
    if err:
        return err

    with get_db() as db:
        add_to_active_list(db, item_name=item_name, user_id=user_id)
        db.commit()
        return f"✓ '{item_name}' added to the shopping list by {user_name}."


@mcp.tool()
def mark_item_purchased(entry_id: int) -> str:
    """
    Mark a shopping list item as purchased.
    This increments the item's purchase count (used for autocomplete sorting).

    Args:
        entry_id: The entry_id from get_shopping_list.
    """
    with get_db() as db:
        mark_as_purchased(db, entry_id)
        db.commit()
        return f"✓ Item (entry {entry_id}) marked as purchased."


@mcp.tool()
def remove_from_shopping_list(entry_id: int) -> str:
    """
    Remove an item from the shopping list without marking it as purchased.
    Use this when an item was added by mistake.

    Args:
        entry_id: The entry_id from get_shopping_list.
    """
    with get_db() as db:
        remove_from_active_list(db, entry_id)
        db.commit()
        return f"✓ Item (entry {entry_id}) removed from the shopping list."


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    import os
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        # SSE mode: used when running inside Docker on a VPS.
        # The client connects over HTTP instead of a stdin/stdout pipe.
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8081"))
        print(f"Starting MCP server (SSE) on {host}:{port}", flush=True)
        mcp.run(transport="sse", host=host, port=port)
    else:
        # stdio mode: used for local development and direct subprocess launch.
        mcp.run()
