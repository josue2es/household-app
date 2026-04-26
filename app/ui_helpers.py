"""
Shared UI helpers.

Every page calls `mobile_layout()` to wrap itself in the standard
mobile shell (header on top, content in the middle, nav on bottom).
"""
from contextlib import contextmanager
from nicegui import ui
from app import auth


# Maximum content width — keeps things readable on tablets/desktop too
MAX_WIDTH = "max-w-md"  # ~448px — typical phone width


@contextmanager
def mobile_layout(title: str, active_tab: str = "tasks"):
    """
    Context manager that renders the standard mobile shell.

    Usage:
        with mobile_layout("My Page", active_tab="tasks"):
            ui.label("This goes in the body")

    Active_tab: "tasks" or "groceries" — highlights the corresponding nav item.
    """
    # Page-wide style: gray background, no scrollbar shift
    ui.query("body").style("background-color: #f3f4f6;")
    ui.query(".nicegui-content").classes("p-0 gap-0")

    # --- Top bar ---
    with ui.header().classes(
        f"bg-primary text-white items-center justify-between px-4 py-3 shadow-md"
    ):
        ui.label(title).classes("text-lg font-semibold")
        with ui.row().classes("items-center gap-2"):
            user_name = auth.current_user_name() or "?"
            color = auth.current_avatar_color()
            with ui.avatar(color=color, size="sm"):
                ui.label(user_name[:1].upper()).classes("text-white text-sm")
            ui.button(icon="logout", on_click=_handle_logout).props("flat round dense color=white")

    # --- Body ---
    with ui.column().classes(f"w-full {MAX_WIDTH} mx-auto p-4 gap-3 pb-24"):
        yield  # caller's content goes here

    # --- Bottom navigation ---
    with ui.footer().classes("bg-white border-t border-gray-200 p-0"):
        with ui.row().classes("w-full justify-around items-center py-2"):
            _nav_button("checklist", "Tasks", "/tasks", active_tab == "tasks")
            _nav_button("shopping_cart", "Groceries", "/groceries", active_tab == "groceries")


def _nav_button(icon: str, label: str, target: str, is_active: bool):
    """One bottom-nav item."""
    color = "text-primary" if is_active else "text-gray-500"
    with ui.column().classes(f"items-center cursor-pointer {color} px-6 py-1").on(
        "click", lambda: ui.navigate.to(target)
    ):
        ui.icon(icon, size="28px")
        ui.label(label).classes("text-xs")


def _handle_logout():
    auth.logout()
    ui.navigate.to("/login")


def show_error(msg: str):
    ui.notify(msg, type="negative", position="top")


def show_success(msg: str):
    ui.notify(msg, type="positive", position="top")