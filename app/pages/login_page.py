"""
Login page — username dropdown + password field.
"""
from nicegui import ui
from app import auth
from app.ui_helpers import show_error


def render():
    """Render the login page."""
    ui.query("body").style("background-color: #f3f4f6;")

    with ui.column().classes("w-full max-w-sm mx-auto p-6 gap-4 mt-12"):
        # Branding
        with ui.column().classes("items-center w-full mb-4"):
            ui.icon("home", size="64px").classes("text-primary")
            ui.label("Hogar").classes("text-2xl font-bold")
            ui.label("Inicia sesión para continuar").classes("text-sm text-gray-500")

        with ui.card().classes("w-full p-6"):
            users = auth.list_users()
            if not users:
                ui.label("No se encontraron usuarios. Ejecuta `python -m app.seed` primero.").classes("text-red-500")
                return

            user_options = {name: name for _, name, _ in users}

            username_select = (
                ui.select(user_options, label="Usuario", value=list(user_options.keys())[0])
                .classes("w-full")
                .props("outlined")
            )
            password_input = (
                ui.input(label="Contraseña", password=True, password_toggle_button=True)
                .classes("w-full")
                .props("outlined")
            )

            def attempt_login():
                user = auth.authenticate(username_select.value, password_input.value)
                if user:
                    auth.login(user)
                    ui.navigate.to("/tasks")
                else:
                    show_error("Usuario o contraseña incorrectos")
                    password_input.value = ""

            # Pressing Enter in password field also logs in
            password_input.on("keydown.enter", attempt_login)

            ui.button("Iniciar sesión", on_click=attempt_login).classes("w-full mt-2").props(
                "size=lg color=primary"
            )

        ui.label("Contraseñas por defecto: alice123 / bob123").classes(
            "text-xs text-gray-400 text-center mt-2"
        )