"""
Login page — tap your name, then type your password.

The phone remembers who logged in last (in the browser's localStorage)
and selects them the next time, so usually only the password is needed.
"""
import json

from nicegui import ui
from app import auth
from app.ui_helpers import show_error

LAST_USER_KEY = "hogar-last-user"

TILE_CLASSES = "w-24 p-3 items-center gap-2 cursor-pointer select-none transition-all"
SELECTED_CLASSES = "hogar-highlight"  # see theme.css


def render():
    """Render the login page."""
    with ui.column().classes("w-full max-w-sm mx-auto px-4 pb-6 pt-14 gap-6"):
        # Branding
        with ui.column().classes("items-center w-full gap-1"):
            ui.image("/pwa/icon-192.png").classes("w-20 h-20 rounded-2xl shadow-md")
            ui.label("Hogar").classes("text-3xl font-bold mt-3")
            ui.label("¿Quién eres?").classes("text-muted")

        users = auth.list_users()
        if not users:
            with ui.card().classes("w-full p-5"):
                ui.label("No se encontraron usuarios. Crea uno desde el CLI de administración.").classes(
                    "text-negative"
                )
            return

        selected = {"name": None}
        tiles: dict[str, ui.card] = {}

        # --- One tile per person ---
        with ui.row().classes("w-full justify-center gap-3"):
            for _, name, color in users:
                with ui.card().classes(TILE_CLASSES).on("click", lambda n=name: select(n)) as tile:
                    with ui.avatar(color=color or "blue", size="56px"):
                        ui.label(name[:1].upper()).classes("text-white text-2xl font-semibold")
                    ui.label(name).classes("text-sm font-medium text-center w-full truncate")
                tile.props["data-user"] = name  # lets the script below find the tile
                tiles[name] = tile

        # --- Password, shown once someone is selected ---
        with ui.card().classes("w-full p-5 gap-3") as password_card:
            greeting = ui.label().classes("font-semibold")
            password_input = (
                ui.input(label="Contraseña", password=True, password_toggle_button=True)
                .classes("w-full")
                .props("outlined")
            )

            def attempt_login():
                user = auth.authenticate(selected["name"] or "", password_input.value or "")
                if user:
                    auth.login(user)
                    ui.navigate.to(auth.home_page(user["role"]))
                else:
                    show_error("Contraseña incorrecta")
                    password_input.value = ""
                    password_input.run_method("focus")

            # Pressing Enter in password field also logs in
            password_input.on("keydown.enter", attempt_login)

            ui.button("Iniciar sesión", on_click=attempt_login).classes("w-full").props(
                "size=lg color=primary"
            )
        password_card.set_visibility(False)

        def select(name: str):
            selected["name"] = name
            for tile_name, tile in tiles.items():
                if tile_name == name:
                    tile.classes(add=SELECTED_CLASSES)
                else:
                    tile.classes(remove=SELECTED_CLASSES)
            greeting.set_text(f"Hola, {name}")
            password_card.set_visibility(True)
            password_input.value = ""
            password_input.run_method("focus")
            ui.run_javascript(
                f"try {{ localStorage.setItem('{LAST_USER_KEY}', {json.dumps(name)}) }} catch (e) {{}}"
            )

        if len(users) == 1:
            select(users[0][1])
        else:
            # Select whoever logged in last on this phone (runs once the page is connected).
            ui.timer(0, lambda: ui.run_javascript(f"""
                try {{
                    const name = localStorage.getItem('{LAST_USER_KEY}');
                    const tile = name && document.querySelector('[data-user="' + CSS.escape(name) + '"]');
                    if (tile) tile.click();
                }} catch (e) {{}}
            """), once=True)
