"""Tasks dashboard."""
from datetime import datetime
from nicegui import ui, run

from app import auth
from app.database import get_db
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_HOUSEKEEPER
from app.ui_helpers import (
    mobile_layout, camera_button, photo_view, photo_url, stars, local_time, show_error,
)
from app.services.photo_service import delete_photo
from app.services.check_service import (
    KIND_PHOTO,
    ensure_daily_checks,
    get_checks,
    submit_photo,
    task_needs_photo,
    undo_proof,
)
from app.services.task_service import (
    LOCAL_TZ,
    SPECIFIC_DATE_TYPES,
    FLEXIBLE_TYPES,
    get_pending_tasks_today,
    get_completed_tasks_for_today,
    get_flexible_urgency,
    complete_task,
    remove_task,
    undo_task_completion,
    get_completion_on,
)

FREQUENCY_LABELS = {
    "once": "Una vez",
    "daily": "Diario",
    "weekly": "Semanal",
    "specific_days": "Días específicos",
    "monthly": "Mensual",
    "weekly_any": "Semanal (libre)",
    "monthly_any": "Mensual (libre)",
    "bimonthly_any": "Bimestral (libre)",
    # every_x_days is formatted dynamically using its config
}

SECTION_LABEL_CLASSES = "text-sm font-semibold text-gray-500 uppercase tracking-wide"


def render(user: dict):
    with mobile_layout("Tareas de hoy", active_tab="tasks"):
        _build_page(user)


def _build_page(user: dict):
    today = datetime.now(LOCAL_TZ).date()

    # The housekeeper's first visit of the day draws the day's checks.
    if user["role"] == ROLE_HOUSEKEEPER:
        ensure_daily_checks(today)

    with get_db() as db:
        photo_checks = []
        for check in get_checks(db, today, KIND_PHOTO):
            done = get_completion_on(db, check.task_id, today)
            photo_checks.append({
                "id": check.id,
                "task_id": check.task_id,
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
            })
    # Photo tasks get their own section, so leave them out of the lists below.
    photo_task_ids = {c["task_id"] for c in photo_checks}

    with get_db() as db:
        pending = get_pending_tasks_today(db)
        flexible_pending = [t for t in pending if t.frequency_type in FLEXIBLE_TYPES]
        urgency = get_flexible_urgency(db, flexible_pending, today)
        pending_data = [
            (
                t.id, t.name, t.description, t.frequency_type, t.frequency_config or {},
                urgency.get(t.id, (None, False))[0],   # days_remaining
                urgency.get(t.id, (None, False))[1],   # is_overdue
            )
            for t in pending
        ]

    with get_db() as db:
        completed = get_completed_tasks_for_today(db)
        completed_data = [
            (task.id, task.name, task.frequency_type, task.frequency_config or {},
             log.id, log.user.name, log.user.avatar_color, log.completed_at)
            for task, log in completed
        ]

    pending_data = [row for row in pending_data if row[0] not in photo_task_ids]
    completed_data = [row for row in completed_data if row[0] not in photo_task_ids]

    # Split pending into specific-date vs flexible
    scheduled = [row for row in pending_data if row[3] in SPECIFIC_DATE_TYPES]
    flexible  = [row for row in pending_data if row[3] not in SPECIFIC_DATE_TYPES]

    # --- CON FOTO ---
    if photo_checks:
        ui.label("Con foto de comprobación").classes(SECTION_LABEL_CLASSES)
        ui.label("Toma una foto del trabajo terminado para completarlas.").classes(
            "text-xs text-gray-500 -mt-2"
        )
        for check in photo_checks:
            _render_photo_check_card(check)
        ui.separator().classes("my-1")

    # --- PENDIENTES (Hoy) ---
    ui.label("Pendientes (Hoy)").classes(SECTION_LABEL_CLASSES)
    if not scheduled:
        with ui.card().classes("w-full p-4 items-center"):
            ui.icon("celebration", size="40px").classes("text-green-500 mb-1")
            ui.label("¡Todo listo por hoy!").classes("text-gray-600 text-sm")
    else:
        for row in scheduled:
            _render_pending_card(*row)

    # --- PENDIENTES (Libre) ---
    if flexible:
        ui.separator().classes("my-1")
        ui.label("Pendientes (Libre)").classes(SECTION_LABEL_CLASSES)
        for row in flexible:
            _render_pending_card(*row)

    # --- COMPLETADAS ---
    if completed_data:
        ui.separator().classes("my-2")
        with ui.row().classes("items-center gap-2"):
            ui.icon("task_alt", size="20px").classes("text-green-600")
            ui.label(f"Completadas ({len(completed_data)})").classes(
                "text-sm font-semibold text-green-600 uppercase tracking-wide"
            )
        for task_id, task_name, ftype, fconfig, log_id, user_name, color, completed_at in completed_data:
            with ui.card().classes("w-full p-3 bg-green-50 border border-green-200"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("check_circle", size="28px").classes("text-green-500")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label(task_name).classes("font-medium text-gray-500 line-through")
                        ui.label(f"{user_name} a las {local_time(completed_at)}").classes(
                            "text-xs text-gray-500"
                        )
                    ui.button(
                        icon="replay",
                        on_click=lambda lid=log_id: do_undo(lid),
                    ).props("flat round dense color=grey").tooltip("Reactivar tarea")

    # --- Add button ---
    if user["role"] in (ROLE_ADMIN, ROLE_MANAGER):
        with ui.page_sticky(position="bottom-right", x_offset=16, y_offset=88):
            ui.button(
                icon="add",
                on_click=lambda: ui.navigate.to("/tasks/new"),
            ).props("fab color=primary")


def _render_photo_check_card(check: dict):
    """One of today's photo tasks: completed by taking a photo."""
    if check["photo_url"] is None:
        with ui.card().classes("w-full p-3 gap-2 border-2 border-amber-400"):
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                ui.icon("photo_camera", size="28px").classes("text-amber-600")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(check["name"]).classes("font-medium text-gray-800")
                    if check["description"]:
                        ui.label(check["description"]).classes("text-xs text-gray-500")
                    if check["done_by"]:
                        ui.label(
                            f"Marcada como hecha por {check['done_by']} a las "
                            f"{check['done_time']}: falta la foto"
                        ).classes("text-xs text-amber-700")
                ui.badge("Requiere foto", color="amber-8").classes("text-xs self-start")

            async def on_photo(image_bytes, check_id=check["id"]):
                user_id = auth.current_user_id()
                if user_id is None:
                    ui.navigate.to("/login")
                    return
                await run.io_bound(submit_photo, check_id, user_id, image_bytes)
                ui.notify("¡Foto guardada y tarea completada!", type="positive", position="top")
                ui.run_javascript("window.location.reload()")

            camera_button("Tomar foto y completar", on_photo).classes("w-full")
        return

    with ui.card().classes("w-full p-3 gap-2 bg-green-50 border border-green-200"):
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            ui.icon("check_circle", size="28px").classes("text-green-500")
            with ui.column().classes("gap-0 flex-1"):
                ui.label(check["name"]).classes("font-medium text-gray-500 line-through")
                ui.label(f"Foto de {check['photo_by']} a las {check['photo_time']}").classes(
                    "text-xs text-gray-500"
                )
            if check["rating"] is None:
                ui.button(
                    icon="replay",
                    on_click=lambda cid=check["id"]: _confirm_undo_proof(cid),
                ).props("flat round dense color=grey").tooltip("Quitar foto y reactivar")
        photo_view(check["photo_url"], classes="w-full h-40 rounded")
        if check["rating"] is None:
            ui.badge("Esperando revisión", color="grey-5").classes("text-xs")
        else:
            with ui.row().classes("items-center gap-2"):
                stars(check["rating"])
                ui.label(f"por {check['reviewer']}").classes("text-xs text-gray-500")
            if check["comment"]:
                ui.label(check["comment"]).classes("text-sm text-gray-700 whitespace-pre-line")


def _confirm_undo_proof(check_id: int):
    with ui.dialog() as dialog, ui.card().classes("w-80 p-5 gap-3"):
        ui.label("¿Quitar la foto?").classes("text-base font-semibold")
        ui.label("La tarea vuelve a pendiente y tendrás que tomar otra foto.").classes(
            "text-sm text-gray-500"
        )
        with ui.row().classes("w-full gap-2 mt-1"):
            ui.button("Cancelar", on_click=dialog.close).classes("flex-1").props(
                "outline color=grey"
            )

            def confirm():
                dialog.close()
                try:
                    with get_db() as db:
                        old_photo = undo_proof(db, check_id)
                except ValueError as e:
                    show_error(str(e))
                    return
                delete_photo(old_photo)
                ui.notify("Tarea reactivada", type="info", position="top")
                ui.run_javascript("window.location.reload()")

            ui.button("Quitar", on_click=confirm).classes("flex-1").props("color=negative")
    dialog.open()


def _render_pending_card(task_id, name, desc, ftype, fconfig,
                         days_remaining=None, is_overdue=False):
    freq_label = (
        f"Cada {fconfig.get('days', '?')} días"
        if ftype == "every_x_days"
        else FREQUENCY_LABELS.get(ftype, ftype)
    )

    # All flexible types get a countdown badge.
    # For every_x_days, suppress countdown once overdue — the deadline passed and
    # "Vence hoy" would be misleading; the red "Atrasado" badge tells the story.
    has_countdown = (
        ftype in FLEXIBLE_TYPES
        and days_remaining is not None
        and not (ftype == "every_x_days" and is_overdue)
    )

    # Countdown badge text and colour.
    countdown_label = countdown_color = None
    if has_countdown:
        if days_remaining == 0:
            countdown_label, countdown_color = "Vence hoy", "negative"
        elif days_remaining == 1:
            countdown_label, countdown_color = "1 día restante", "warning"
        elif days_remaining <= 3:
            countdown_label, countdown_color = f"{days_remaining} días restantes", "warning"
        else:
            countdown_label, countdown_color = f"{days_remaining} días restantes", "grey-5"

    # Card and text styling change when overdue.
    if is_overdue:
        card_cls  = "w-full p-3 bg-red-50 border border-red-300"
        name_cls  = "font-medium text-red-800"
    else:
        card_cls  = "w-full p-3"
        name_cls  = "font-medium text-gray-800"

    with ui.card().classes(card_cls):
        with ui.row().classes("w-full items-center gap-3"):
            ui.button(
                icon="radio_button_unchecked",
                on_click=lambda tid=task_id: do_complete(tid),
            ).props("flat round size=md color=primary")

            with ui.column().classes("gap-0 flex-1"):
                ui.label(name).classes(name_cls)
                if desc:
                    ui.label(desc).classes("text-xs text-gray-500")
                with ui.row().classes("gap-1 mt-1 flex-wrap"):
                    ui.badge(freq_label, color="grey-4").classes("text-xs")
                    if countdown_label:
                        ui.badge(countdown_label, color=countdown_color).classes("text-xs")

            # "Atrasado" sits at the far right of the row, above the badges.
            if is_overdue:
                ui.badge("Atrasado", color="negative").classes("text-xs self-start")


def do_complete(task_id):
    user_id = auth.current_user_id()
    if user_id is None:
        ui.navigate.to("/login")
        return
    with get_db() as db:
        # The page may predate today's draw: photo tasks need their photo.
        if task_needs_photo(db, task_id, datetime.now(LOCAL_TZ).date()):
            ui.notify("Esta tarea requiere una foto", type="warning", position="top")
            ui.run_javascript('window.location.reload()')
            return
        complete_task(db, task_id, user_id)
        db.commit()
    ui.notify("¡Tarea completada!", type="positive", position="top")
    ui.run_javascript('window.location.reload()')


def do_undo(log_id):
    with get_db() as db:
        undo_task_completion(db, log_id)
        db.commit()
    ui.notify("Tarea reactivada", type="info", position="top")
    ui.run_javascript('window.location.reload()')
