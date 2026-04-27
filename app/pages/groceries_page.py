"""
Groceries page — Module 2.

Smart-add input (autocomplete from catalog) + checklist of pending items.
Category is only asked when adding a brand-new item not already in the catalog.
"""
from nicegui import ui
from app import auth
from app.database import get_db
from app.ui_helpers import mobile_layout, show_success, show_error
from app.services.grocery_service import (
    get_active_list,
    search_suggestions,
    add_to_active_list,
    mark_as_purchased,
    remove_from_active_list,
)


CATEGORIES = [
    "Despensa",
    "Frescos",
    "Carnes y Lácteos",
    "Panadería",
    "Cuidado Personal",
    "Limpieza del Hogar",
    "Mascotas",
    "Otros",
]


def render():
    with mobile_layout("Lista de compras", active_tab="groceries"):
        container = ui.column().classes("w-full gap-3")

        def refresh():
            container.clear()
            with container:
                _render_smart_add(refresh)
                _render_active_list(refresh)

        refresh()


def _render_smart_add(refresh_fn):
    with ui.card().classes("w-full p-3 gap-3"):
        with get_db() as db:
            all_items = search_suggestions(db, query="", limit=None)

        # Names list drives the native autocomplete (browser datalist — always works).
        all_names = [item.name for item in all_items]
        # Lowercase set for fast "does this exist?" check at add-time.
        known = {item.name.lower() for item in all_items}

        name_input = (
            ui.input(
                label="Agregar artículo (escribe para buscar o crear)",
                autocomplete=all_names,
            )
            .classes("w-full")
            .props("outlined clearable")
        )

        def add_item():
            raw = (name_input.value or "").strip()
            if not raw:
                show_error("Escribe o selecciona un artículo primero")
                return
            user_id = auth.current_user_id()
            if user_id is None:
                ui.navigate.to("/login")
                return

            if raw.lower() in known:
                # Existing catalog item — category already stored in DB, no need to ask.
                _do_add(raw, None, user_id, name_input, refresh_fn)
            else:
                # Brand-new item — ask for category before saving.
                _show_category_dialog(raw, user_id, name_input, refresh_fn)

        ui.button("Agregar a la lista", icon="add", on_click=add_item).classes("w-full").props(
            "color=primary"
        )


def _do_add(item_name: str, category: str | None, user_id: int, name_input, refresh_fn):
    """Persist the item and refresh. Category is ignored for existing catalog items."""
    try:
        with get_db() as db:
            add_to_active_list(
                db,
                item_name=item_name,
                user_id=user_id,
                category=category or "Otros",
            )
        show_success(f"'{item_name}' agregado")
        name_input.set_value("")
        refresh_fn()
    except ValueError as e:
        show_error(str(e))


def _show_category_dialog(item_name: str, user_id: int, name_input, refresh_fn):
    """Modal that appears only when the user is adding an item not yet in the catalog."""
    with ui.dialog() as dialog, ui.card().classes("w-80 p-5 gap-3"):
        ui.label("Artículo nuevo").classes("text-base font-semibold")
        ui.label(
            f'"{item_name}" no está en el catálogo. ¿A qué categoría pertenece?'
        ).classes("text-sm text-gray-500")

        cat_select = (
            ui.select(CATEGORIES, value=CATEGORIES[0], label="Categoría")
            .classes("w-full")
            .props("outlined")
        )

        with ui.row().classes("w-full gap-2 mt-1"):
            ui.button("Cancelar", on_click=dialog.close).classes("flex-1").props(
                "outline color=grey"
            )

            def confirm():
                chosen = cat_select.value
                dialog.close()
                _do_add(item_name, chosen, user_id, name_input, refresh_fn)

            ui.button("Agregar", on_click=confirm).classes("flex-1").props("color=primary")

    dialog.open()


def _render_active_list(refresh_fn):
    """Pending items grouped by category."""
    with get_db() as db:
        active = get_active_list(db)
        active_data = [
            (entry.id, entry.item.name, entry.item.category, entry.added_by.name)
            for entry in active
        ]

    if not active_data:
        with ui.card().classes("w-full p-6 items-center"):
            ui.icon("shopping_basket", size="48px").classes("text-gray-300 mb-2")
            ui.label("Tu lista está vacía").classes("text-gray-600")
            ui.label("Agrega un artículo arriba para comenzar").classes("text-xs text-gray-400")
        return

    by_cat: dict[str, list] = {}
    for entry_id, name, category, added_by in active_data:
        by_cat.setdefault(category, []).append((entry_id, name, added_by))

    for category in sorted(by_cat.keys()):
        ui.label(category).classes(
            "text-sm font-semibold text-gray-500 uppercase tracking-wide mt-2"
        )
        for entry_id, name, added_by in by_cat[category]:
            _render_grocery_card(entry_id, name, added_by, refresh_fn)


def _render_grocery_card(entry_id: int, name: str, added_by: str, refresh_fn):
    with ui.card().classes("w-full p-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.row().classes("items-center gap-3 flex-1"):
                ui.button(icon="radio_button_unchecked").props(
                    "flat round size=md color=primary"
                ).on_click(lambda eid=entry_id: _on_purchased(eid, refresh_fn))

                with ui.column().classes("gap-0 flex-1"):
                    ui.label(name).classes("font-medium text-gray-800")
                    ui.label(f"agregado por {added_by}").classes("text-xs text-gray-500")

            with ui.button(icon="more_vert").props("flat round dense color=grey"):
                with ui.menu():
                    ui.menu_item(
                        "Eliminar (no comprado)",
                        on_click=lambda eid=entry_id: _on_removed(eid, refresh_fn),
                    ).props("dense")


def _on_purchased(entry_id: int, refresh_fn):
    with get_db() as db:
        mark_as_purchased(db, entry_id)
    show_success("¡Marcado como comprado!")
    refresh_fn()


def _on_removed(entry_id: int, refresh_fn):
    with get_db() as db:
        remove_from_active_list(db, entry_id)
    show_success("Eliminado")
    refresh_fn()
