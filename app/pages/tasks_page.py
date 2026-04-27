"""Tasks dashboard."""
from datetime import timezone
from nicegui import ui

from app.services.task_service import LOCAL_TZ  # single definition, shared with service

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
from app import auth
from app.database import get_db
from app.ui_helpers import mobile_layout, show_success
from app.services.task_service import (
    get_pending_tasks_today,
    get_completed_tasks_for_today,
    complete_task,
    remove_task,
    undo_task_completion,
)


def render():
    with mobile_layout("Tareas de hoy", active_tab="tasks"):
        _build_page()


def _build_page():
    # --- Pending section ---
    with get_db() as db:
        pending = get_pending_tasks_today(db)
        pending_data = [
            (t.id, t.name, t.description, t.frequency_type, t.frequency_config or {})
            for t in pending
        ]

    with get_db() as db:
        completed = get_completed_tasks_for_today(db)
        completed_data = [
            (task.id, task.name, task.frequency_type, task.frequency_config or {},
             log.id, log.user.name, log.user.avatar_color, log.completed_at)
            for task, log in completed
        ]

    ui.label("Pendientes").classes("text-sm font-semibold text-gray-500 uppercase tracking-wide")

    if not pending_data:
        with ui.card().classes("w-full p-6 items-center"):
            ui.icon("celebration", size="48px").classes("text-green-500 mb-2")
            ui.label("¡Todo listo por hoy!").classes("text-gray-700")
    else:
        for task_id, name, desc, ftype, fconfig in pending_data:
            with ui.card().classes("w-full p-3"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.button(
                        icon="radio_button_unchecked",
                        on_click=lambda tid=task_id: do_complete(tid),
                    ).props("flat round size=md color=primary")

                    with ui.column().classes("gap-0 flex-1"):
                        ui.label(name).classes("font-medium text-gray-800")
                        if desc:
                            ui.label(desc).classes("text-xs text-gray-500")
                        badge_label = (
                            f"Cada {fconfig.get('days', '?')} días"
                            if ftype == "every_x_days"
                            else FREQUENCY_LABELS.get(ftype, ftype)
                        )
                        ui.badge(badge_label, color="grey-4").classes("text-xs mt-1")

    # --- Completed section ---
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
                        ui.label(
                            f"{user_name} a las {local_time.strftime('%H:%M')}"
                        ).classes("text-xs text-gray-500")
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
