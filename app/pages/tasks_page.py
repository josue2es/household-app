"""Tasks dashboard."""
from datetime import datetime, timezone
from nicegui import ui

from app import auth
from app.database import get_db
from app.ui_helpers import mobile_layout
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


def render():
    with mobile_layout("Tareas de hoy", active_tab="tasks"):
        _build_page()


def _build_page():
    today = datetime.now(LOCAL_TZ).date()

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

    # Split pending into specific-date vs flexible
    scheduled = [row for row in pending_data if row[3] in SPECIFIC_DATE_TYPES]
    flexible  = [row for row in pending_data if row[3] not in SPECIFIC_DATE_TYPES]

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
            local_time = completed_at.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
            with ui.card().classes("w-full p-3 bg-green-50 border border-green-200"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("check_circle", size="28px").classes("text-green-500")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label(task_name).classes("font-medium text-gray-500 line-through")
                        ui.label(f"{user_name} a las {local_time.strftime('%H:%M')}").classes(
                            "text-xs text-gray-500"
                        )
                    ui.button(
                        icon="replay",
                        on_click=lambda lid=log_id: do_undo(lid),
                    ).props("flat round dense color=grey").tooltip("Reactivar tarea")

    # --- Add button ---
    with ui.page_sticky(position="bottom-right", x_offset=16, y_offset=88):
        ui.button(
            icon="add",
            on_click=lambda: ui.navigate.to("/tasks/new"),
        ).props("fab color=primary")


def _render_pending_card(task_id, name, desc, ftype, fconfig,
                         days_remaining=None, is_overdue=False):
    freq_label = (
        f"Cada {fconfig.get('days', '?')} días"
        if ftype == "every_x_days"
        else FREQUENCY_LABELS.get(ftype, ftype)
    )

    # Only period-based flexible types get a countdown badge.
    has_countdown = ftype in ("weekly_any", "monthly_any", "bimonthly_any") and days_remaining is not None

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
