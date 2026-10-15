"""Tasks dashboard."""
from datetime import datetime
from nicegui import ui, run

from app import auth
from app.database import get_db
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_HOUSEKEEPER
from app.ui_helpers import (
    mobile_layout, camera_button, photo_view, photo_url, stars, local_time, show_error,
    format_day, section_title, pill, check_circle_button, undo_snackbar,
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


def render(user: dict):
    today = datetime.now(LOCAL_TZ).date()
    with mobile_layout("Tareas de hoy", active_tab="tasks", subtitle=format_day(today).capitalize()):
        # Kept across refreshes, so an opened "Completadas" list stays open.
        view = {"show_done": False}

        # Defined inside render(), not at module level: a module-level
        # refreshable would refresh the page of everyone who has it open.
        @ui.refreshable
        def content():
            _build_page(user, view, content.refresh)

        content()

        # --- Add button ---
        if user["role"] in (ROLE_ADMIN, ROLE_MANAGER):
            with ui.page_sticky(position="bottom-right", x_offset=20, y_offset=104):
                ui.button(
                    icon="add",
                    on_click=lambda: ui.navigate.to("/tasks/new"),
                ).props("fab color=primary aria-label='Nueva tarea'")


def _build_page(user: dict, view: dict, refresh):
    """The page's content. `refresh()` rebuilds it in place after a change."""
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

    # --- Today's progress ---
    photos_taken = sum(1 for c in photo_checks if c["photo_url"])
    done_count = len(completed_data) + photos_taken
    left_count = len(scheduled) + len(photo_checks) - photos_taken
    _render_progress(user["name"], done_count, done_count + left_count, len(flexible))

    # --- CON FOTO ---
    if photo_checks:
        section_title("Con foto de comprobación")
        ui.label("Toma una foto del trabajo terminado para completarlas.").classes(
            "text-xs text-muted -mt-2 px-1"
        )
        for check in photo_checks:
            _render_photo_check_card(check, refresh)

    # --- PENDIENTES (Hoy) ---
    section_title("Pendientes (Hoy)", len(scheduled))
    if not scheduled:
        with ui.card().classes("w-full p-4"):
            with ui.row().classes("items-center gap-3 no-wrap"):
                ui.icon("celebration", size="28px").classes("text-positive")
                ui.label("¡Todo listo por hoy!").classes("text-muted")
    else:
        with ui.card().classes("w-full p-0 gap-0 overflow-hidden"):
            for row in scheduled:
                _render_pending_row(refresh, *row)

    # --- PENDIENTES (Libre) ---
    if flexible:
        section_title("Pendientes (Libre)", len(flexible))
        ui.label("Sin día fijo: hazlas cualquier día antes de que venzan.").classes(
            "text-xs text-muted -mt-2 px-1"
        )
        with ui.card().classes("w-full p-0 gap-0 overflow-hidden"):
            for row in flexible:
                _render_pending_row(refresh, *row)

    # --- COMPLETADAS (folded away, so the page shows what's left to do) ---
    if completed_data:
        with ui.card().classes("w-full p-0 gap-0 overflow-hidden mt-2"):
            with ui.expansion(f"Completadas hoy ({len(completed_data)})", icon="task_alt").classes(
                "w-full hogar-flush"
            ).props("header-class='text-positive font-semibold'").bind_value(view, "show_done"):
                for _, task_name, _, _, log_id, user_name, color, completed_at in completed_data:
                    _render_completed_row(refresh, task_name, log_id, user_name, color, completed_at)


def _render_progress(name: str, done: int, total: int, flexible_left: int):
    """Greeting and how much of today's work is done."""
    with ui.card().classes("w-full p-4"):
        with ui.row().classes("w-full items-center gap-4 no-wrap"):
            with ui.column().classes("gap-0 flex-1 min-w-0"):
                ui.label(f"Hola, {name}").classes("text-lg font-bold")
                # Impersonal wording: admins and managers see this page too.
                left = total - done
                if total == 0:
                    message = "No hay tareas con fecha de hoy"
                elif left == 0:
                    message = "¡Todo listo por hoy! 🎉"
                elif left == 1:
                    message = "Falta 1 tarea para hoy"
                else:
                    message = f"Faltan {left} tareas para hoy"
                ui.label(message).classes("text-sm text-muted")
                if flexible_left:
                    ui.label(
                        f"y {flexible_left} sin día fijo" if left else
                        f"Quedan {flexible_left} sin día fijo"
                    ).classes("text-xs text-muted")
            if total:
                color = "positive" if done == total else "primary"
                with ui.circular_progress(
                    value=done, min=0, max=total, show_value=False, size="64px", color=color,
                ).props("show-value track-color=grey-3 thickness=0.18 rounded"):
                    ui.label(f"{done}/{total}").classes("text-sm font-bold text-gray-800")


def _render_photo_check_card(check: dict, refresh):
    """One of today's photo tasks: completed by taking a photo."""
    if check["photo_url"] is None:
        with ui.card().classes("w-full p-4 gap-3"):
            with ui.row().classes("w-full items-start gap-3 no-wrap"):
                with ui.element("div").classes("rounded-full bg-amber-100 text-amber-700 p-2 flex"):
                    ui.icon("photo_camera", size="22px")
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label(check["name"]).classes("font-medium")
                    if check["description"]:
                        ui.label(check["description"]).classes("text-xs text-muted")
                    if check["done_by"]:
                        ui.label(
                            f"Marcada como hecha por {check['done_by']} a las "
                            f"{check['done_time']}: falta la foto"
                        ).classes("text-xs text-amber-800 mt-1")
                pill("Requiere foto", "warning")

            async def on_photo(image_bytes, check_id=check["id"]):
                user_id = auth.current_user_id()
                if user_id is None:
                    ui.navigate.to("/login")
                    return
                await run.io_bound(submit_photo, check_id, user_id, image_bytes)
                ui.notify("¡Foto guardada y tarea completada!", type="positive", position="top")
                refresh()

            camera_button("Tomar foto y completar", on_photo).classes("w-full")
        return

    with ui.card().classes("w-full p-4 gap-3"):
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            ui.icon("check_circle", size="28px").classes("text-positive")
            with ui.column().classes("gap-0 flex-1 min-w-0"):
                ui.label(check["name"]).classes("font-medium text-muted line-through")
                ui.label(f"Foto de {check['photo_by']} a las {check['photo_time']}").classes(
                    "text-xs text-muted"
                )
            if check["rating"] is None:
                ui.button(
                    icon="undo",
                    on_click=lambda cid=check["id"]: _confirm_undo_proof(cid, refresh),
                ).props("flat round dense color=grey-7 aria-label='Quitar foto y reactivar'")
        photo_view(check["photo_url"], classes="w-full h-40 rounded-xl")
        if check["rating"] is None:
            pill("Esperando revisión", icon="hourglass_empty")
        else:
            with ui.row().classes("items-center gap-2"):
                stars(check["rating"])
                ui.label(f"por {check['reviewer']}").classes("text-xs text-muted")
            if check["comment"]:
                ui.label(check["comment"]).classes("text-sm whitespace-pre-line")


def _confirm_undo_proof(check_id: int, refresh):
    with ui.dialog() as dialog, ui.card().classes("w-80 p-5 gap-3"):
        ui.label("¿Quitar la foto?").classes("text-base font-semibold")
        ui.label("La tarea vuelve a pendiente y tendrás que tomar otra foto.").classes(
            "text-sm text-muted"
        )
        with ui.row().classes("w-full gap-2 mt-1"):
            ui.button("Cancelar", on_click=dialog.close).classes("flex-1").props(
                "outline color=grey-7"
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
                refresh()

            ui.button("Quitar", on_click=confirm).classes("flex-1").props("color=negative")
    dialog.open()


def _render_pending_row(refresh, task_id, name, desc, ftype, fconfig,
                        days_remaining=None, is_overdue=False):
    freq_label = (
        f"Cada {fconfig.get('days', '?')} días"
        if ftype == "every_x_days"
        else FREQUENCY_LABELS.get(ftype, ftype)
    )

    # All flexible types get a countdown label.
    # For every_x_days, suppress countdown once overdue — the deadline passed and
    # "Vence hoy" would be misleading; the red "Atrasado" label tells the story.
    has_countdown = (
        ftype in FLEXIBLE_TYPES
        and days_remaining is not None
        and not (ftype == "every_x_days" and is_overdue)
    )

    # Countdown text and tone (colors in theme.css).
    countdown_label = countdown_tone = None
    if has_countdown:
        if days_remaining == 0:
            countdown_label, countdown_tone = "Vence hoy", "danger"
        elif days_remaining == 1:
            countdown_label, countdown_tone = "1 día restante", "warning"
        elif days_remaining <= 3:
            countdown_label, countdown_tone = f"{days_remaining} días restantes", "warning"
        else:
            countdown_label, countdown_tone = f"{days_remaining} días restantes", "neutral"

    with ui.element("div").classes("hogar-row" + (" bg-red-50" if is_overdue else "")):
        check_circle_button(lambda: _complete(task_id, name, refresh))
        with ui.column().classes("gap-1 flex-1 min-w-0"):
            with ui.column().classes("gap-0"):
                ui.label(name).classes(
                    "font-medium leading-snug" + (" text-red-800" if is_overdue else "")
                )
                if desc:
                    ui.label(desc).classes("text-xs text-muted")
            with ui.row().classes("gap-1 flex-wrap"):
                pill(freq_label)
                if is_overdue:
                    pill("Atrasado", "danger", icon="schedule")
                if countdown_label:
                    pill(countdown_label, countdown_tone)


def _render_completed_row(refresh, task_name, log_id, user_name, color, completed_at):
    with ui.element("div").classes("hogar-row"):
        ui.icon("check_circle", size="28px").classes("text-positive mx-1.5")
        with ui.column().classes("gap-0 flex-1 min-w-0"):
            ui.label(task_name).classes("font-medium text-muted line-through")
            with ui.row().classes("items-center gap-1"):
                with ui.avatar(color=color or "blue", size="16px"):
                    ui.label(user_name[:1].upper()).classes("text-white text-[10px]")
                ui.label(f"{user_name} · {local_time(completed_at)}").classes("text-xs text-muted")
        ui.button(
            icon="undo",
            on_click=lambda: _undo(log_id, refresh, notify=True),
        ).props("flat round dense color=grey-7 aria-label='Reactivar tarea'")


def _complete(task_id: int, name: str, refresh):
    user_id = auth.current_user_id()
    if user_id is None:
        ui.navigate.to("/login")
        return
    with get_db() as db:
        # The page may predate today's draw: photo tasks need their photo.
        if task_needs_photo(db, task_id, datetime.now(LOCAL_TZ).date()):
            ui.notify("Esta tarea requiere una foto", type="warning", position="top")
            refresh()
            return
        log_id = complete_task(db, task_id, user_id).id
        db.commit()
    refresh()
    undo_snackbar(f"«{name}» completada", lambda: _undo(log_id, refresh))


def _undo(log_id: int, refresh, notify: bool = False):
    with get_db() as db:
        undo_task_completion(db, log_id)
        db.commit()
    if notify:
        ui.notify("Tarea reactivada", type="info", position="top")
    refresh()
