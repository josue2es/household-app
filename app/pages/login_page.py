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
            ui.label("Household").classes("text-2xl font-bold")
            ui.label("Sign in to continue").classes("text-sm text-gray-500")

        with ui.card().classes("w-full p-6"):
            users = auth.list_users()
            if not users:
                ui.label("No users found. Run `python -m app.seed` first.").classes("text-red-500")
                return

            user_options = {name: name for _, name, _ in users}

            username_select = (
                ui.select(user_options, label="User", value=list(user_options.keys())[0])
                .classes("w-full")
                .props("outlined")
            )
            password_input = (
                ui.input(label="Password", password=True, password_toggle_button=True)
                .classes("w-full")
                .props("outlined")
            )

            def attempt_login():
                user = auth.authenticate(username_select.value, password_input.value)
                if user:
                    auth.login(user)
                    ui.navigate.to("/tasks")
                else:
                    show_error("Invalid username or password")
                    password_input.value = ""

            # Pressing Enter in password field also logs in
            password_input.on("keydown.enter", attempt_login)

            ui.button("Sign In", on_click=attempt_login).classes("w-full mt-2").props(
                "size=lg color=primary"
            )

        ui.label("Default passwords: alice123 / bob123").classes(
            "text-xs text-gray-400 text-center mt-2"
        )