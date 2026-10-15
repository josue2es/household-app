"""
Review page — the manager rates the day's checks.

Two sections per day (see check_service.py for the rules):
  - "Fotos de la ama de llaves": the photos she took as proof. The manager
    looks at each one and rates it from 1 to 5 stars, with a comment.
  - "Inspecciones": tasks the manager checks in person. They take a photo
    and rate it the same way. The housekeeper can't see these until rated.

Admins see the same page read-only.
"""
from datetime import date, timedelta
from nicegui import ui, run

from app import auth
from app.database import get_db
from app.models import ROLE_MANAGER, ROLE_LABELS, ROLE_HOUSEKEEPER, TaskCheck
from app.ui_helpers import (
    mobile_layout, camera_button, photo_view, photo_url, stars, star_rating,
    format_day, local_time, show_error, show_success, section_title, pill, empty_state,
    refresh_nav,
)
from app.services.task_service import get_completion_on
from app.services.check_service import (
    KIND_PHOTO,
    KIND_INSPECTION,
    local_today,
    get_checks,
    can_review,
    submit_photo,
    review_check,
    pending_review_days,
    average_rating,
)

HOUSEKEEPER = ROLE_LABELS[ROLE_HOUSEKEEPER].lower()


def render(user: dict, day: str | None = None):
    today = local_today()
    try:
        shown_day = min(date.fromisoformat(day), today) if day else today
    except ValueError:
        shown_day = today
    can_edit = user["role"] == ROLE_MANAGER

    with mobile_layout("Revisión", active_tab="review"):
        # Defined inside render(), not at module level: a module-level
        # refreshable would refresh the page of everyone who has it open.
        @ui.refreshable
        def content():
            _build_page(shown_day, today, can_edit, refresh)

        def refresh():
            content.refresh()
            refresh_nav()  # the "pending reviews" counter

        content()


def _build_page(day: date, today: date, can_edit: bool, refresh):
    """The page's content. `refresh()` rebuilds it in place after a change."""
    with get_db() as db:
        photo_checks = [_check_data(db, c, today) for c in get_checks(db, day, KIND_PHOTO)]
        inspections = [_check_data(db, c, today) for c in get_checks(db, day, KIND_INSPECTION)]
        earlier_pending = pending_review_days(db, today) if day == today else []
        avg, count = average_rating(db, today - timedelta(days=29))

    _day_navigator(day, today)

    if earlier_pending:
        with ui.card().classes("w-full p-3 gap-2 bg-amber-50 border-amber-200"):
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.icon("history", size="20px").classes("text-amber-800")
                ui.label("Pendientes de días anteriores").classes("text-sm font-semibold text-amber-900")
            with ui.row().classes("gap-1 flex-wrap"):
                for d in earlier_pending:
                    ui.chip(
                        format_day(d),
                        on_click=lambda d=d: ui.navigate.to(f"/review?day={d}"),
                    ).props("clickable color=amber-2 text-color=amber-10")

    if count:
        with ui.row().classes("w-full items-center gap-2 px-1"):
            ui.label("Promedio últimos 30 días:").classes("text-sm text-muted")
            ui.label(f"{avg:.1f}").classes("text-sm font-semibold")
            stars(avg, size="xs")
            ui.label(f"({count})").classes("text-xs text-muted")

    if not photo_checks and not inspections:
        empty_state(
            "event_busy",
            "No hay revisiones este día",
            f"Las tareas a revisar se sortean cuando la {HOUSEKEEPER} abre la app.",
        )
        return

    section_title(f"Fotos de la {HOUSEKEEPER}")
    if not photo_checks:
        ui.label("No había tareas para foto este día.").classes("text-sm text-muted px-1")
    for check in photo_checks:
        _render_check_card(check, can_edit, refresh)

    section_title("Inspecciones")
    if can_edit:
        ui.label(
            f"Revisa estas tareas en persona y toma una foto. La {HOUSEKEEPER} no sabe cuáles son."
        ).classes("text-xs text-muted -mt-2 px-1")
    if not inspections:
        ui.label("No había más tareas para inspeccionar este día.").classes("text-sm text-muted px-1")
    for check in inspections:
        _render_check_card(check, can_edit, refresh)


def _check_data(db, check: TaskCheck, today: date) -> dict:
    """Everything a card shows, as plain data (the DB session closes after this)."""
    done = get_completion_on(db, check.task_id, check.day)
    return {
        "id": check.id,
        "kind": check.kind,
        "name": check.task.name,
        "description": check.task.description,
        "photo_url": photo_url(check.id, check.photo_path) if check.photo_path else None,
        "photo_by": check.photo_by.name if check.photo_by else "",
        "photo_time": local_time(check.photo_at) if check.photo_at else "",
        "done_by": done.user.name if done else None,
        "done_time": local_time(done.completed_at) if done else "",
        "rating": check.rating,
        "comment": check.comment or "",
        "reviewer": check.reviewed_by.name if check.reviewed_by else "",
        "can_review": can_review(check, today),
    }


def _day_navigator(day: date, today: date):
    with ui.card().classes("w-full p-1"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.button(
                icon="chevron_left",
                on_click=lambda: ui.navigate.to(f"/review?day={day - timedelta(days=1)}"),
            ).props("flat round color=primary aria-label='Día anterior'")
            with ui.column().classes("items-center gap-0"):
                ui.label("Hoy" if day == today else format_day(day).capitalize()).classes(
                    "font-semibold"
                )
                if day == today:
                    ui.label(format_day(day)).classes("text-xs text-muted")
                else:
                    ui.link("Volver a hoy", "/review").classes("text-xs text-primary")
            next_button = ui.button(
                icon="chevron_right",
                on_click=lambda: ui.navigate.to(f"/review?day={day + timedelta(days=1)}"),
            ).props("flat round color=primary aria-label='Día siguiente'")
            if day >= today:
                next_button.disable()


def _render_check_card(check: dict, can_edit: bool, refresh):
    with ui.card().classes("w-full p-4 gap-3"):
        with ui.row().classes("w-full items-start gap-2 no-wrap"):
            with ui.column().classes("gap-0 flex-1 min-w-0"):
                ui.label(check["name"]).classes("font-medium")
                if check["description"]:
                    ui.label(check["description"]).classes("text-xs text-muted")
            if check["rating"] is None:
                pill("Sin evaluar")
            else:
                pill("Evaluada", "success", icon="check")

        if check["done_by"]:
            with ui.row().classes("items-center gap-1 -mt-1"):
                ui.icon("check_circle", size="16px").classes("text-positive")
                ui.label(
                    f"Marcada como hecha por {check['done_by']} a las {check['done_time']}"
                ).classes("text-xs text-green-800")
        else:
            ui.label("No se marcó como hecha").classes("text-xs text-muted -mt-1")

        if check["photo_url"]:
            photo_view(check["photo_url"])
            ui.label(f"Foto de {check['photo_by']} a las {check['photo_time']}").classes(
                "text-xs text-muted -mt-1"
            )
        elif check["kind"] == KIND_PHOTO:
            _photo_placeholder("Aún no hay foto")
        elif not can_edit:
            _photo_placeholder("Aún no se inspecciona")

        if check["kind"] == KIND_INSPECTION and can_edit:
            async def on_photo(image_bytes, check_id=check["id"]):
                manager_id = _manager_id()
                if manager_id is None:
                    return
                await run.io_bound(submit_photo, check_id, manager_id, image_bytes)
                show_success("Foto guardada")
                refresh()

            if check["photo_url"]:
                camera_button("Cambiar foto", on_photo, props="outline color=primary").classes(
                    "w-full"
                )
            else:
                camera_button("Tomar foto de inspección", on_photo).classes("w-full")

        _render_review(check, can_edit, refresh)


def _photo_placeholder(text: str):
    with ui.element("div").classes(
        "w-full h-24 rounded-xl bg-gray-100 flex items-center justify-center gap-2 text-gray-400"
    ):
        ui.icon("no_photography", size="24px")
        ui.label(text).classes("text-sm")


def _render_review(check: dict, can_edit: bool, refresh):
    if check["rating"] is not None:
        with ui.column().classes("w-full gap-1 bg-gray-50 rounded-xl p-3"):
            with ui.row().classes("items-center gap-2"):
                stars(check["rating"])
                ui.label(f"por {check['reviewer']}").classes("text-xs text-muted")
            ui.label(check["comment"] or "Sin comentarios").classes(
                "text-sm whitespace-pre-line"
            )
        if can_edit:
            form = ui.column().classes("w-full gap-2")
            form.set_visibility(False)
            with form:
                _review_form(check, refresh)
            edit_button = ui.button("Editar evaluación", icon="edit").props("flat dense color=primary")
            edit_button.on_click(lambda: (form.set_visibility(True), edit_button.set_visibility(False)))
        return

    if not can_edit:
        ui.label("Pendiente de evaluación").classes("text-xs text-muted italic")
    elif check["can_review"]:
        _review_form(check, refresh)
    elif check["kind"] == KIND_PHOTO:
        ui.label("Podrás evaluarla cuando llegue la foto.").classes("text-xs text-muted italic")


def _review_form(check: dict, refresh):
    ui.label("¿Qué tan bien quedó?").classes("text-sm text-muted")
    rating = star_rating(value=check["rating"] or 0, size="lg")
    comment = (
        ui.textarea("Comentario: qué estuvo mal o qué mejorar (opcional)", value=check["comment"])
        .classes("w-full")
        .props("outlined autogrow")
    )

    def save():
        manager_id = _manager_id()
        if manager_id is None:
            return
        try:
            with get_db() as db:
                review_check(db, check["id"], manager_id, rating.value, comment.value)
        except ValueError as e:
            show_error(str(e))
            return
        show_success("Evaluación guardada")
        refresh()

    ui.button("Guardar evaluación", icon="save", on_click=save).classes("w-full").props(
        "color=primary"
    )


def _manager_id() -> int | None:
    """The acting manager's id; sends anyone else to the login page."""
    user = auth.current_user()
    if user is None or user["role"] != ROLE_MANAGER:
        ui.navigate.to("/login")
        return None
    return user["id"]
