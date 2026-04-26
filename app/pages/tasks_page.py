"""Tasks dashboard."""
from nicegui import ui
from datetime import timezone, timedelta
LOCAL_TZ = timezone(timedelta(hours=-6))

FREQUENCY_LABELS = {
    "once": "Una vez",
    "daily": "Diario",
    "weekly": "Semanal",
    "specific_days": "Días específicos",
    "monthly": "Mensual",
}
from app import auth
from app.database import get_db
from app.ui_helpers import mobile_layout, show_success
from app.services.task_service import (
    get_pending_tasks_today,
    get_completed_tasks_today,
    complete_task,
    remove_task,
)


def render():
    with mobile_layout("Tareas de hoy", active_tab="tasks"):
        _build_page()


def _build_page():
    # --- Pending section ---
    with get_db() as db:
        pending = get_pending_tasks_today(db)
        pending_data = [(t.id, t.name, t.description, t.frequency_type) for t in pending]

    with get_db() as db:
        logs = get_completed_tasks_today(db)
        log_data = [
            (log.task.name, log.user.name, log.user.avatar_color, log.completed_at)
            for log in logs
        ]

    ui.label("Pendientes").classes("text-sm font-semibold text-gray-500 uppercase tracking-wide")

    if not pending_data:
        with ui.card().classes("w-full p-6 items-center"):
            ui.icon("celebration", size="48px").classes("text-green-500 mb-2")
            ui.label("¡Todo listo por hoy!").classes("text-gray-700")
    else:
        for task_id, name, desc, ftype in pending_data:
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
                        ui.badge(FREQUENCY_LABELS.get(ftype, ftype), color="grey-4").classes("text-xs mt-1")

    # --- Completed section ---
    if log_data:
        ui.separator().classes("my-2")
        with ui.row().classes("items-center gap-2"):
            ui.icon("task_alt", size="20px").classes("text-green-600")
            ui.label(f"Completadas ({len(log_data)})").classes(
                "text-sm font-semibold text-green-600 uppercase tracking-wide"
            )

        for task_name, user_name, color, completed_at in log_data:
            local_time = completed_at.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
            with ui.card().classes("w-full p-3 bg-green-50 border border-green-200"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("check_circle", size="28px").classes("text-green-500")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label(task_name).classes("font-medium text-gray-500 line-through")
                        ui.label(
                            f"{user_name} a las {local_time.strftime('%H:%M')}"
                        ).classes("text-xs text-gray-500")

    # --- Add button ---
    with ui.page_sticky(position="bottom-right", x_offset=16, y_offset=88):
        ui.button(
            icon="add",
            on_click=lambda: ui.navigate.to("/tasks/new"),
        ).props("fab color=primary")


def do_complete(task_id):
    """Called when the user taps the circle."""
    user_id = auth.current_user_id()
    if user_id is None:
        ui.navigate.to("/login")
        return
    with get_db() as db:
        complete_task(db, task_id, user_id)
        db.commit()
    ui.notify("¡Tarea completada!", type="positive", position="top")
    js_code = f'window.location.reload()'
    ui.run_javascript(js_code)