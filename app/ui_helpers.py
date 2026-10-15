"""
Shared UI helpers.

Every page calls `mobile_layout()` to wrap itself in the standard
mobile shell (header on top, content in the middle, nav on bottom).
The look itself (colors, rounded cards, ...) is in theme.py and
static/theme.css.
"""
import logging
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from nicegui import app, context, ui
from app import auth
from app.database import get_db
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_HOUSEKEEPER, ROLE_LABELS
from app.services.task_service import LOCAL_TZ
from app.services.check_service import (
    local_today,
    pending_review_count,
    unseen_feedback_count,
)
from app.services.photo_service import PhotoError

log = logging.getLogger("household.photo")

# Maximum content width — keeps things readable on tablets/desktop too
MAX_WIDTH = "max-w-md"  # ~448px — typical phone width

# Bottom navigation: tab key → (icon, label, page)
NAV_ITEMS = {
    "tasks": ("checklist", "Tareas", "/tasks"),
    "groceries": ("shopping_cart", "Compras", "/groceries"),
    "review": ("fact_check", "Revisión", "/review"),
    "feedback": ("star_rate", "Evaluaciones", "/feedback"),
    "users": ("group", "Usuarios", "/users"),
}

# Which tabs each role sees, in order. Must match the page guards in main.py.
NAV_BY_ROLE = {
    ROLE_ADMIN: ["tasks", "review", "groceries", "users"],
    ROLE_MANAGER: ["review", "tasks", "groceries"],
    ROLE_HOUSEKEEPER: ["tasks", "groceries", "feedback"],
}

# Largest photo the browser will upload (phone photos are usually 2-8 MB).
MAX_PHOTO_BYTES = 15_000_000

WEEKDAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTH_NAMES = ["ene", "feb", "mar", "abr", "may", "jun",
               "jul", "ago", "sep", "oct", "nov", "dic"]


@contextmanager
def mobile_layout(title: str, active_tab: str = "tasks", subtitle: str = ""):
    """
    Context manager that renders the standard mobile shell.

    Usage:
        with mobile_layout("My Page", active_tab="tasks"):
            ui.label("This goes in the body")

    active_tab: a key of NAV_ITEMS — highlights the corresponding nav item.
    The nav shows the tabs of the logged-in user's role (NAV_BY_ROLE).
    subtitle: optional small line under the title (e.g. today's date).
    """
    user = auth.current_user() or {}
    role = user.get("role", ROLE_HOUSEKEEPER)

    ui.query(".nicegui-content").classes("p-0 gap-0")

    # --- Top bar: page title, and the user's avatar with the account menu ---
    with ui.header().classes("hogar-header items-center justify-between px-4 no-wrap"):
        with ui.column().classes("gap-0 min-w-0"):
            ui.label(title).classes("text-xl font-bold leading-tight truncate")
            if subtitle:
                ui.label(subtitle).classes("text-xs text-muted")
        _account_menu(user)

    # --- Body ---
    with ui.column().classes(f"w-full {MAX_WIDTH} mx-auto p-4 gap-3 pb-28"):
        yield  # caller's content goes here

    # --- Bottom navigation ---
    with ui.footer().classes("hogar-nav p-0"):
        @ui.refreshable
        def nav():
            badges = _nav_badges(role)
            with ui.row().classes(f"w-full {MAX_WIDTH} mx-auto items-stretch gap-0 no-wrap"):
                for key in NAV_BY_ROLE.get(role, []):
                    icon, label, target = NAV_ITEMS[key]
                    _nav_button(icon, label, target, key == active_tab, badges.get(key, 0))

        nav()
    app.storage.client["refresh_nav"] = nav.refresh


def refresh_nav():
    """Update the counters on the bottom nav, e.g. after a review is saved."""
    refresh = app.storage.client.get("refresh_nav")
    if refresh is not None:
        refresh()


def _account_menu(user: dict):
    """
    The user's avatar; tapping it opens a menu with their name, role and
    "Cerrar sesión". Logging out takes two taps, so it can't happen by accident.
    """
    name = user.get("name") or "?"
    with ui.button().props("flat round dense aria-label='Cuenta'"):
        with ui.avatar(color=user.get("avatar_color") or "blue", size="36px"):
            ui.label(name[:1].upper()).classes("text-white text-base font-semibold")
        with ui.menu().props("anchor='bottom right' self='top right'").classes("rounded-xl"):
            with ui.column().classes("gap-0 px-4 pt-3 pb-2"):
                ui.label(name).classes("font-semibold")
                ui.label(ROLE_LABELS.get(user.get("role"), "")).classes("text-xs text-muted")
            ui.separator()
            with ui.menu_item(on_click=_handle_logout).classes("gap-3 text-negative"):
                ui.icon("logout", size="20px")
                ui.label("Cerrar sesión")


def _nav_badges(role: str) -> dict[str, int]:
    """Counters on the nav: what waits on this user."""
    with get_db() as db:
        if role == ROLE_HOUSEKEEPER:
            return {"feedback": unseen_feedback_count(db)}
        if role == ROLE_MANAGER:
            return {"review": pending_review_count(db, local_today())}
    return {}


def _nav_button(icon: str, label: str, target: str, is_active: bool, badge: int = 0):
    """
    One bottom-nav item: a plain link, so the browser starts loading the
    page on tap. The current tab gets a tinted pill behind its icon.
    """
    link = ui.element("a").props(f'href="{target}"').classes(
        "hogar-nav__item" + (" hogar-nav__item--active" if is_active else "")
    )
    if is_active:
        link.props('aria-current="page"')
    with link:
        with ui.element("div").classes("hogar-nav__icon"):
            ui.icon(icon, size="24px")
            if badge:
                # A sibling of the icon, not a child: inside the icon the
                # number would be drawn with the icon font and not show.
                ui.label(str(badge)).classes("hogar-nav__badge")
        ui.label(label)


def _handle_logout():
    auth.logout()
    ui.navigate.to("/login")


def show_error(msg: str):
    ui.notify(msg, type="negative", position="top")


def show_success(msg: str):
    ui.notify(msg, type="positive", position="top")


def undo_snackbar(message: str, on_undo: Callable[[], None], seconds: float = 6) -> None:
    """
    A dark bar above the bottom nav with a "Deshacer" button, shown for a few
    seconds after an action that's easy to do by mistake (completing a task,
    marking an item as bought). A new one replaces the previous one.

    It's added to the page layout, not to the current container, so it
    survives the page content being refreshed.
    """
    previous = app.storage.client.get("snackbar")
    if previous is not None and not previous.is_deleted:
        previous.delete()

    with context.client.layout:
        with ui.element("div").classes("hogar-snackbar").props('role="status"') as bar:
            ui.label(message).classes("flex-1 min-w-0")

            def undo():
                bar.delete()
                on_undo()

            ui.button("Deshacer", on_click=undo).props("flat dense color=amber-4 padding='6px 12px'")

        def hide():
            if not bar.is_deleted:
                bar.delete()

        ui.timer(seconds, hide, once=True)
    app.storage.client["snackbar"] = bar


# ---------- Building blocks ----------

def section_title(text: str, count: int | None = None):
    """An uppercase title above a group of cards, with an optional count."""
    with ui.element("div").classes("hogar-section"):
        ui.label(text)
        if count is not None:
            ui.label(str(count)).classes("font-medium normal-case")


def pill(text: str, tone: str = "neutral", icon: str | None = None):
    """
    A small rounded label. tone: neutral, info, success, warning or danger
    (colors in theme.css).
    """
    with ui.element("span").classes(f"pill pill-{tone}"):
        if icon:
            ui.icon(icon, size="14px")
        ui.label(text)


def empty_state(icon: str, title: str, subtitle: str = "", color: str = "text-gray-300"):
    """A friendly placeholder card for a list with nothing in it."""
    with ui.card().classes("w-full p-6 items-center gap-1"):
        ui.icon(icon, size="48px").classes(f"{color} mb-1")
        ui.label(title).classes("font-medium text-center")
        if subtitle:
            ui.label(subtitle).classes("text-sm text-muted text-center")


def check_circle_button(on_click: Callable[[], None], *, label: str = "Marcar como hecha"):
    """The empty circle you tap to tick something off."""
    return (
        ui.button(icon="radio_button_unchecked", on_click=on_click)
        .props("flat round color=primary size=lg padding='6px'")
        .props(f'aria-label="{label}"')
    )


# ---------- Dates and times ----------

def format_day(d: date) -> str:
    """'lunes 12 oct' — a short Spanish date label."""
    return f"{WEEKDAY_NAMES[d.weekday()]} {d.day} {MONTH_NAMES[d.month - 1]}"


def local_time(utc_naive: datetime) -> str:
    """'14:05' — a DB timestamp (UTC-naive) as local time."""
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime("%H:%M")


# ---------- Photos ----------

def photo_url(check_id: int, photo_path: str) -> str:
    """
    URL of a check's photo (served by the /photos route in main.py).
    The file name changes with every new photo, so `?v=` stops the browser
    from showing an old cached one.
    """
    return f"/photos/{check_id}?v={Path(photo_path).stem}"


def photo_view(url: str, classes: str = "w-full h-48 rounded-xl"):
    """A photo that opens full screen when tapped."""
    with ui.dialog().props("maximized") as dialog:
        with ui.element("div").classes("w-full h-full bg-black flex items-center justify-center").on(
            "click", dialog.close
        ):
            ui.image(url).props("fit=contain").classes("w-full h-full")
    ui.image(url).props("fit=cover").classes(f"{classes} cursor-pointer").on("click", dialog.open)


def stars(rating: float, size: str = "sm"):
    """Read-only star rating; averages are shown to the nearest half star."""
    star_rating(value=round(rating * 2) / 2, size=size).props("readonly")


def star_rating(value: float = 0, size: str = "sm") -> ui.rating:
    """1-5 stars; empty stars are outlined so it's clear which ones are selected."""
    return ui.rating(value=value, max=5, icon="star_border", icon_selected="star",
                     icon_half="star_half", color="amber", size=size)


def camera_button(label: str, on_photo, *, icon: str = "photo_camera",
                  props: str = "color=primary") -> ui.button:
    """
    A button that opens the phone's rear camera. The photo is uploaded and
    passed to `await on_photo(image_bytes)`.

    Same technique as "Identificar con foto" on the groceries page: a hidden
    ui.upload whose file input gets capture="environment", clicked from the
    browser directly (a file dialog only opens from a real tap). Desktop
    browsers ignore `capture` and show a file picker instead.

    `on_photo` may raise ValueError (or PhotoError) with a message for the
    user; any other error is logged and shown as an unexpected error.
    """
    progress = {"notification": None}

    def hide_progress():
        if progress["notification"] is not None:
            progress["notification"].dismiss()
            progress["notification"] = None

    def show_progress(message: str):
        hide_progress()
        progress["notification"] = ui.notification(message, spinner=True, timeout=None)

    async def handle_upload(e):
        show_progress("Guardando foto…")
        try:
            image_bytes = await e.file.read()
            upload.reset()
            await on_photo(image_bytes)
        except (ValueError, PhotoError) as err:
            if isinstance(err, PhotoError):
                log.warning("Unreadable task photo: %s", err.detail)
            show_error(str(err))
        except Exception as err:
            log.exception("Unexpected error while saving a task photo")
            show_error(f"Error inesperado al guardar la foto ({type(err).__name__})")
        finally:
            hide_progress()

    def handle_rejected():
        show_error(f"La foto no se pudo subir: debe ser una imagen de menos de "
                   f"{MAX_PHOTO_BYTES / 1e6:.0f} MB")
        upload.reset()

    def handle_failed():
        hide_progress()
        show_error("La foto no se pudo subir: revisa tu conexión e intenta de nuevo")
        upload.reset()

    upload = (
        ui.upload(
            auto_upload=True,
            max_files=1,
            max_file_size=MAX_PHOTO_BYTES,
            on_begin_upload=lambda: show_progress("Subiendo foto…"),
            on_upload=handle_upload,
            on_rejected=handle_rejected,
        )
        .props('accept="image/*"')
        .classes("hidden")
    )
    upload.on("failed", handle_failed)

    button = ui.button(label, icon=icon).props(props)
    button.on(
        "click",
        js_handler=f"""() => {{
            const up = document.getElementById('c{upload.id}');
            const input = up && up.querySelector('input[type=file]');
            if (input) {{
                input.setAttribute('accept', 'image/*');
                input.setAttribute('capture', 'environment');
                input.click();
            }}
        }}""",
    )
    return button
