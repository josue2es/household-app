"""
Feedback page — the housekeeper reads the manager's ratings and comments.

Shows both kinds of checks once rated: her own proof photos and the
manager's inspections. Opening the page marks the new ones as seen, which
clears the badge on the "Evaluaciones" tab.
"""
from datetime import timedelta
from nicegui import ui

from app.database import get_db
from app.ui_helpers import mobile_layout, photo_view, photo_url, stars, format_day
from app.services.check_service import (
    KIND_PHOTO,
    local_today,
    get_feedback,
    mark_feedback_seen,
    average_rating,
)

# How far back the list goes.
FEEDBACK_DAYS = 60

KIND_LABELS = {KIND_PHOTO: "Tu foto"}  # anything else is an inspection


def render(user: dict):
    with mobile_layout("Evaluaciones", active_tab="feedback"):
        _build_page()


def _build_page():
    today = local_today()
    with get_db() as db:
        avg, count = average_rating(db, today - timedelta(days=29))
        items = [
            {
                "id": c.id,
                "day": c.day,
                "kind": KIND_LABELS.get(c.kind, "Inspección"),
                "name": c.task.name,
                "rating": c.rating,
                "comment": c.comment or "",
                "reviewer": c.reviewed_by.name if c.reviewed_by else "",
                "photo_url": photo_url(c.id, c.photo_path) if c.photo_path else None,
                "is_new": c.seen_at is None,
            }
            for c in get_feedback(db, today - timedelta(days=FEEDBACK_DAYS))
        ]
        # Shown now with a "Nuevo" badge; seen from the next visit on.
        mark_feedback_seen(db, [item["id"] for item in items if item["is_new"]])

    with ui.card().classes("w-full p-4 items-center gap-1"):
        if count:
            ui.label(f"{avg:.1f}").classes("text-4xl font-bold text-gray-800")
            stars(avg, size="md")
            ui.label(f"Promedio de {count} evaluaciones en los últimos 30 días").classes(
                "text-xs text-gray-500 text-center"
            )
        else:
            ui.icon("star_outline", size="40px").classes("text-gray-300")
            ui.label("Aún no tienes evaluaciones").classes("text-gray-600")
            ui.label("Aquí verás las estrellas y comentarios sobre tu trabajo.").classes(
                "text-xs text-gray-400 text-center"
            )

    for item in items:
        _render_feedback_card(item)


def _render_feedback_card(item: dict):
    border = "border-2 border-blue-400" if item["is_new"] else ""
    with ui.card().classes(f"w-full p-3 gap-2 {border}"):
        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            ui.label(format_day(item["day"]).capitalize()).classes("text-xs text-gray-500 flex-1")
            ui.badge(item["kind"], color="grey-5").classes("text-xs")
            if item["is_new"]:
                ui.badge("Nuevo", color="primary").classes("text-xs")
        ui.label(item["name"]).classes("font-medium text-gray-800")
        with ui.row().classes("items-center gap-2"):
            stars(item["rating"])
            ui.label(f"por {item['reviewer']}").classes("text-xs text-gray-500")
        if item["comment"]:
            with ui.row().classes("w-full items-start gap-2 no-wrap bg-amber-50 rounded p-2"):
                ui.icon("chat", size="18px").classes("text-amber-700 mt-0.5")
                ui.label(item["comment"]).classes("text-sm text-gray-800 whitespace-pre-line")
        if item["photo_url"]:
            photo_view(item["photo_url"], classes="w-full h-40 rounded")
