"""
Groceries page — Module 2.

Smart-add combo box (sorted by purchase frequency) + checklist of pending items.
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
    """The combo box that suggests previously-bought items, sorted by frequency."""
    with ui.card().classes("w-full p-3"):
        with get_db() as db:
            initial = search_suggestions(db, query="", limit=None)
            options = {item.name: f"{item.name} ({item.purchase_count}x)" for item in initial}

        # NiceGUI's `ui.select` with `with_input=True` becomes a searchable combo box.
        # `new_value_mode='add-unique'` lets the user type a brand-new item name.
        item_select = (
            ui.select(
                options=options,
                with_input=True,
                new_value_mode="add-unique",
                label="Agregar artículo (escribe para buscar o crear)",
            )
            .classes("w-full")
            .props("outlined use-input fill-input hide-selected")
        )

        category_select = (
            ui.select(CATEGORIES, value="Despensa", label="Categoría")
            .classes("w-full")
            .props("outlined")
        )

        def add_item():
            value = item_select.value
            if not value:
                show_error("Escribe o selecciona un artículo primero")
                return
            user_id = auth.current_user_id()
            if user_id is None:
                ui.navigate.to("/login")
                return
            try:
                with get_db() as db:
                    add_to_active_list(
                        db,
                        item_name=str(value),
                        user_id=user_id,
                        category=category_select.value,
                    )
                show_success(f"'{value}' agregado")
                refresh_fn()
            except ValueError as e:
                show_error(str(e))

        ui.button("Agregar a la lista", icon="add", on_click=add_item).classes("w-full").props(
            "color=primary"
        )


def _render_active_list(refresh_fn):
    """The checklist — pending items grouped by category."""
    with get_db() as db:
        active = get_active_list(db)
        # Detach
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

    # Group by category
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
                # Tap circle = mark as purchased
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