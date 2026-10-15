"""
Users page — the admin creates and manages manager and housekeeper accounts.

Admin accounts are listed but managed with the Admin CLI only
(see user_service.py).
"""
from nicegui import ui

from app import auth
from app.database import get_db
from app.models import ROLE_ADMIN, ROLE_LABELS
from app.ui_helpers import mobile_layout, show_error, show_success
from app.services.user_service import (
    MANAGED_ROLES,
    AVATAR_COLORS,
    MIN_PASSWORD_LENGTH,
    list_users,
    create_user,
    set_password,
    set_role,
    set_active,
)


def render(user: dict):
    with mobile_layout("Usuarios", active_tab="users"):
        container = ui.column().classes("w-full gap-3")

        def refresh():
            container.clear()
            with container:
                _build_page(refresh)

        refresh()


def _build_page(refresh_fn):
    with get_db() as db:
        users = [
            (u.id, u.name, u.role, u.avatar_color, u.is_active)
            for u in list_users(db)
        ]

    ui.button(
        "Nuevo usuario", icon="person_add", on_click=lambda: _new_user_dialog(refresh_fn)
    ).classes("w-full").props("color=primary")

    for user_id, name, role, color, is_active in users:
        _render_user_card(user_id, name, role, color, is_active, refresh_fn)


def _render_user_card(user_id, name, role, color, is_active, refresh_fn):
    card_cls = "w-full p-3" if is_active else "w-full p-3 bg-gray-100"
    with ui.card().classes(card_cls):
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            with ui.avatar(color=color if is_active else "grey", size="md"):
                ui.label(name[:1].upper()).classes("text-white")
            with ui.column().classes("gap-0 flex-1"):
                ui.label(name).classes(
                    "font-medium " + ("text-gray-800" if is_active else "text-gray-500 line-through")
                )
                with ui.row().classes("gap-1 items-center"):
                    ui.label(ROLE_LABELS.get(role, role)).classes("text-xs text-gray-500")
                    if not is_active:
                        ui.badge("Desactivado", color="grey-6").classes("text-xs")

            if role not in MANAGED_ROLES:
                ui.label("Desde el CLI").classes("text-xs text-gray-400")
                return

            other_role = next(r for r in MANAGED_ROLES if r != role)
            with ui.button(icon="more_vert").props("flat round dense color=grey"):
                with ui.menu():
                    ui.menu_item(
                        "Cambiar contraseña",
                        on_click=lambda: _password_dialog(user_id, name),
                    ).props("dense")
                    ui.menu_item(
                        f"Cambiar a {ROLE_LABELS[other_role]}",
                        on_click=lambda: _apply(
                            lambda db: set_role(db, user_id, other_role),
                            f"{name} ahora es {ROLE_LABELS[other_role]}",
                            refresh_fn,
                        ),
                    ).props("dense")
                    if is_active:
                        ui.menu_item(
                            "Desactivar (no podrá entrar)",
                            on_click=lambda: _apply(
                                lambda db: set_active(db, user_id, False),
                                f"{name} desactivado",
                                refresh_fn,
                            ),
                        ).props("dense")
                    else:
                        ui.menu_item(
                            "Activar",
                            on_click=lambda: _apply(
                                lambda db: set_active(db, user_id, True),
                                f"{name} activado",
                                refresh_fn,
                            ),
                        ).props("dense")


def _is_admin() -> bool:
    """Whether the acting user is (still) an admin; sends anyone else to the login page."""
    user = auth.current_user()
    if user is None or user["role"] != ROLE_ADMIN:
        ui.navigate.to("/login")
        return False
    return True


def _apply(change, message: str, refresh_fn):
    """Run `change(db)`, then report and refresh."""
    if not _is_admin():
        return
    try:
        with get_db() as db:
            change(db)
    except ValueError as e:
        show_error(str(e))
        return
    show_success(message)
    refresh_fn()


def _password_inputs():
    """A password field and its confirmation."""
    hint = f"Mínimo {MIN_PASSWORD_LENGTH} caracteres"
    first = (
        ui.input("Contraseña", password=True, password_toggle_button=True)
        .classes("w-full")
        .props(f'outlined hint="{hint}"')
    )
    second = (
        ui.input("Repetir contraseña", password=True, password_toggle_button=True)
        .classes("w-full")
        .props("outlined")
    )
    return first, second


def _color_picker(initial: str) -> dict:
    """
    A row of colored circles for the avatar color; the chosen one has a
    check mark. Returns a dict whose "value" is the chosen color.
    """
    chosen = {"value": initial}
    ui.label("Color").classes("text-sm text-muted -mb-1")

    @ui.refreshable
    def swatches():
        with ui.row().classes("gap-2"):
            for color in AVATAR_COLORS:
                ui.button(
                    icon="check" if color == chosen["value"] else None,
                    on_click=lambda c=color: (chosen.update(value=c), swatches.refresh()),
                ).props(f"round size=sm color={color} aria-label={color}")

    swatches()
    return chosen


def _new_user_dialog(refresh_fn):
    with ui.dialog() as dialog, ui.card().classes("w-80 p-5 gap-3"):
        ui.label("Nuevo usuario").classes("text-base font-semibold")
        name_input = ui.input("Nombre").classes("w-full").props("outlined")
        role_select = (
            ui.select({r: ROLE_LABELS[r] for r in MANAGED_ROLES}, value=MANAGED_ROLES[-1], label="Rol")
            .classes("w-full")
            .props("outlined")
        )
        color = _color_picker("teal")
        password_input, repeat_input = _password_inputs()

        with ui.row().classes("w-full gap-2 mt-1"):
            ui.button("Cancelar", on_click=dialog.close).classes("flex-1").props(
                "outline color=grey"
            )

            def confirm():
                if not _is_admin():
                    return
                if password_input.value != repeat_input.value:
                    show_error("Las contraseñas no coinciden")
                    return
                try:
                    with get_db() as db:
                        create_user(db, name_input.value or "", role_select.value,
                                    color["value"], password_input.value or "")
                except ValueError as e:
                    show_error(str(e))
                    return
                dialog.close()
                show_success(f"Usuario '{name_input.value.strip()}' creado")
                refresh_fn()

            ui.button("Crear", on_click=confirm).classes("flex-1").props("color=primary")

    dialog.open()


def _password_dialog(user_id: int, name: str):
    with ui.dialog() as dialog, ui.card().classes("w-80 p-5 gap-3"):
        ui.label(f"Nueva contraseña para {name}").classes("text-base font-semibold")
        password_input, repeat_input = _password_inputs()

        with ui.row().classes("w-full gap-2 mt-1"):
            ui.button("Cancelar", on_click=dialog.close).classes("flex-1").props(
                "outline color=grey"
            )

            def confirm():
                if not _is_admin():
                    return
                if password_input.value != repeat_input.value:
                    show_error("Las contraseñas no coinciden")
                    return
                try:
                    with get_db() as db:
                        set_password(db, user_id, password_input.value or "")
                except ValueError as e:
                    show_error(str(e))
                    return
                dialog.close()
                show_success(f"Contraseña de {name} cambiada")

            ui.button("Guardar", on_click=confirm).classes("flex-1").props("color=primary")

    dialog.open()
