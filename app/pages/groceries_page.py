"""
Groceries page — Module 2.

Smart-add input (autocomplete from catalog) + checklist of pending items.
Category is only asked when adding a brand-new item not already in the catalog.
"""
import logging
import os
import secrets

from nicegui import ui
from app import auth
from app.database import get_db
from app.models import ROLE_ADMIN
from app.ui_helpers import mobile_layout, show_success, show_error, empty_state, undo_snackbar
from app.services.grocery_service import (
    CATEGORIES,
    get_active_list,
    search_suggestions,
    add_to_active_list,
    mark_as_purchased,
    undo_purchase,
    remove_from_active_list,
)
from app.services.vision_service import (
    identify_grocery_from_photo,
    VisionError,
    VisionUnrecognized,
)

log = logging.getLogger("household.photo")

# Largest photo the browser will upload (phone photos are usually 2-8 MB).
MAX_PHOTO_BYTES = 15_000_000

# An icon for each category (Material Icons names); others get "category".
CATEGORY_ICONS = {
    "Despensa": "inventory_2",
    "Frescos": "eco",
    "Carnes y Lácteos": "egg",
    "Panadería": "bakery_dining",
    "Cuidado Personal": "soap",
    "Limpieza del Hogar": "cleaning_services",
    "Mascotas": "pets",
    "Otros": "category",
}


def render():
    user = auth.current_user() or {}
    with mobile_layout("Lista de compras", active_tab="groceries"):
        # What the add field needs to know, kept up to date as items are added:
        #   categories: catalog item name (lowercase) → its category
        #   on_list:    names (lowercase) already on the shopping list
        catalog = {"categories": {}, "on_list": set()}

        # Defined inside render(), not at module level: a module-level
        # refreshable would refresh the page of everyone who has it open.
        @ui.refreshable
        def shopping_list():
            _render_active_list(catalog, shopping_list.refresh)

        def after_add():
            _load_catalog(catalog, name_input)
            shopping_list.refresh()

        name_input = _render_smart_add(catalog, after_add, user.get("role") == ROLE_ADMIN)
        _load_catalog(catalog, name_input)
        shopping_list()


def _load_catalog(catalog: dict, name_input):
    """Read the catalog for the add field's suggestions and category lookup."""
    with get_db() as db:
        all_items = search_suggestions(db, query="", limit=None)
        # Extract plain strings inside the session before it closes.
        names = [item.name for item in all_items]
        catalog["categories"] = {item.name.lower(): item.category for item in all_items}
    name_input.set_autocomplete(names)


def _render_smart_add(catalog: dict, on_added, is_admin: bool):
    """The add field, with the camera and add buttons next to it. Returns the field."""
    with ui.card().classes("w-full p-3 gap-2"):
        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            name_input = (
                ui.input(placeholder="Agregar artículo…")
                .classes("flex-1")
                .props("outlined dense clearable")
            )
            photo_ready = _render_photo_identify(name_input, catalog, on_added)

            def add_item():
                raw = (name_input.value or "").strip()
                if not raw:
                    show_error("Escribe o selecciona un artículo primero")
                    return
                if raw.lower() in catalog["on_list"]:
                    ui.notify(f"«{raw}» ya está en la lista", type="info", position="top")
                    name_input.set_value("")
                    return
                user_id = auth.current_user_id()
                if user_id is None:
                    ui.navigate.to("/login")
                    return

                if raw.lower() in catalog["categories"]:
                    # Existing catalog item — category already stored in DB, no need to ask.
                    _do_add(raw, None, user_id, name_input, on_added)
                else:
                    # Brand-new item — ask for category before saving.
                    _show_category_dialog(raw, user_id, name_input, on_added)

            ui.button(icon="add", on_click=add_item).props(
                "round color=primary aria-label='Agregar a la lista'"
            )

        # The keyboard's Enter / "Ir" key adds too.
        name_input.on("keydown.enter", add_item)

        ui.label(
            "Escribe para buscar en el catálogo, o un nombre nuevo para crearlo."
            + (" Con 📷 puedes identificarlo con una foto." if photo_ready else "")
        ).classes("text-xs text-muted px-1")
        if not photo_ready and is_admin:
            ui.label("Configura GEMINI_API_KEY para identificar artículos con foto.").classes(
                "text-xs text-muted px-1"
            )
    return name_input


def _render_photo_identify(name_input, catalog: dict, on_added) -> bool:
    """
    Camera button that identifies a product via Gemini. Returns False (and
    shows nothing) when GEMINI_API_KEY isn't set.

    Every outcome is reported on screen: progress while the photo uploads and
    Gemini looks at it, then either the identified product or a problem that
    stays visible until closed. Problems show their technical reason and a
    reference code that matches the server log line for that attempt.
    """
    if not os.getenv("GEMINI_API_KEY"):
        return False
    progress = {"notification": None}

    def show_progress(message: str):
        if progress["notification"] is None:
            progress["notification"] = ui.notification(message, spinner=True, timeout=None)
        else:
            progress["notification"].message = message

    def hide_progress():
        if progress["notification"] is not None:
            progress["notification"].dismiss()
            progress["notification"] = None

    async def handle_photo(e):
        ref = secrets.token_hex(3)  # short code shown to the user and written to the log
        show_progress("Identificando artículo…")
        try:
            image_bytes = await e.file.read()
            mime = e.file.content_type or "image/jpeg"
            with get_db() as db:
                catalog_names = [i.name for i in search_suggestions(db, query="", limit=300)]
            name, category = await identify_grocery_from_photo(
                image_bytes, mime, catalog_names, ref=ref
            )
        except VisionUnrecognized as err:
            _notify_problem(str(err), f"Prueba otra foto o escríbelo manualmente · Ref {ref}",
                            type="warning")
            return
        except VisionError as err:  # already logged by the vision service
            _notify_problem(str(err), f"{err.detail} · Ref {ref}")
            return
        except Exception as err:
            log.exception("[%s] Unexpected error while identifying a photo", ref)
            _notify_problem("Error inesperado al identificar la foto",
                            f"{type(err).__name__}: {err} · Ref {ref}")
            return
        finally:
            hide_progress()
            upload.reset()

        ui.notify(f"Artículo identificado: {name}", type="positive", position="top")
        _show_photo_confirm_dialog(name, category, catalog["categories"], name_input, on_added)

    def handle_rejected(e):
        """The browser refused the file before uploading it (too big, not an image, ...)."""
        ref = secrets.token_hex(3)
        reasons = []
        for entry in e.args.get("files", []):
            if entry.get("reason") == "max-file-size":
                reasons.append(f"pesa {entry.get('size', 0) / 1e6:.1f} MB; el máximo es "
                               f"{MAX_PHOTO_BYTES / 1e6:.0f} MB")
            elif entry.get("reason") == "accept":
                reasons.append(f"no es una imagen ({entry.get('type') or entry.get('name')})")
            else:
                reasons.append(str(entry.get("reason")))
        log.warning("[%s] Photo upload rejected by the browser: %s", ref, e.args)
        _notify_problem("La foto no se pudo subir", f"{'; '.join(reasons)} · Ref {ref}")
        upload.reset()

    def handle_failed(e):
        """The upload itself failed (connection lost, proxy refused it, ...)."""
        ref = secrets.token_hex(3)
        status = e.args.get("status", 0)
        reason = f"HTTP {status} {e.args.get('response', '')}".strip() if status else \
            "sin conexión con el servidor"
        log.error("[%s] Photo upload failed: %s", ref, e.args)
        hide_progress()
        _notify_problem("La foto no se pudo subir", f"{reason} · Ref {ref}")
        upload.reset()

    upload = (
        ui.upload(
            auto_upload=True,
            max_files=1,
            max_file_size=MAX_PHOTO_BYTES,
            on_begin_upload=lambda: show_progress("Subiendo foto…"),
            on_upload=handle_photo,
        )
        .props('accept="image/*"')
        .classes("hidden")
    )
    # Quasar's own events carry the details NiceGUI's on_rejected leaves out.
    upload.on("rejected", handle_rejected, js_handler="""(entries) => emit({files: entries.map(
        (e) => ({reason: e.failedPropValidation, name: e.file.name, size: e.file.size, type: e.file.type}))})""")
    upload.on("failed", handle_failed, js_handler="""(info) => emit({
        status: info.xhr ? info.xhr.status : 0,
        response: info.xhr ? String(info.xhr.responseText || '').slice(0, 200) : ''})""")

    photo_btn = ui.button(icon="photo_camera").props(
        "round outline color=primary aria-label='Identificar con foto'"
    )
    photo_btn.on(
        "click",
        js_handler=f"""() => {{
            const up = document.getElementById('c{upload.id}');
            const input = up && up.querySelector('input[type=file]');
            if (input) {{
                input.setAttribute('accept', 'image/*');
                input.setAttribute('capture', 'environment');
                input.click();
            }}
        }}""",
    )
    return True


def _notify_problem(message: str, caption: str, type: str = "negative"):
    """A notification that stays on screen until closed, so a problem can't go unnoticed."""
    ui.notify(message, caption=caption, type=type, position="top", multi_line=True,
              timeout=0, actions=[{"label": "Cerrar", "color": "white"}])


def _do_add(item_name: str, category: str | None, user_id: int, name_input, on_added):
    """Persist the item and refresh. Category is ignored for existing catalog items."""
    try:
        with get_db() as db:
            add_to_active_list(
                db,
                item_name=item_name,
                user_id=user_id,
                category=category or "Otros",
            )
        show_success(f"«{item_name}» agregado")
        name_input.set_value("")
        on_added()
    except ValueError as e:
        show_error(str(e))


def _show_category_dialog(item_name: str, user_id: int, name_input, on_added):
    """
    Modal that appears only when the user is adding an item not yet in the
    catalog. Tapping a category adds the item right away.
    """
    with ui.dialog() as dialog, ui.card().classes("w-80 p-5 gap-3"):
        ui.label("Artículo nuevo").classes("text-base font-semibold")
        ui.label(
            f"«{item_name}» no está en el catálogo. ¿A qué categoría pertenece?"
        ).classes("text-sm text-muted")

        def choose(category: str):
            dialog.close()
            _do_add(item_name, category, user_id, name_input, on_added)

        with ui.element("div").classes("grid grid-cols-2 gap-2 w-full"):
            for category in CATEGORIES:
                with ui.button(on_click=lambda c=category: choose(c)).props(
                    "outline color=grey-8 align=left padding='8px 10px'"
                ).classes("w-full"):
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        ui.icon(CATEGORY_ICONS.get(category, "category"), size="20px").classes(
                            "text-primary"
                        )
                        ui.label(category).classes("text-sm text-left leading-tight")

        ui.button("Cancelar", on_click=dialog.close).classes("w-full").props("flat color=grey-7")

    dialog.open()


def _show_photo_confirm_dialog(
    name: str,
    category: str,
    known_categories: dict[str, str],
    name_input,
    on_added,
):
    """Modal shown after Gemini identifies a product from a photo."""
    # If the item already exists in the catalog, its stored category wins
    # anyway (add_to_active_list ignores the passed category in that case),
    # so pre-select it instead of showing a category that won't stick.
    existing_category = known_categories.get(name.lower())
    initial_category = existing_category or category

    with ui.dialog() as dialog, ui.card().classes("w-80 p-5 gap-3"):
        ui.label("Producto identificado").classes("text-base font-semibold")
        ui.label("Revisa el nombre y la categoría antes de agregar.").classes(
            "text-sm text-muted"
        )

        name_field = (
            ui.input(label="Nombre", value=name).classes("w-full").props("outlined")
        )
        cat_select = (
            ui.select(CATEGORIES, value=initial_category, label="Categoría")
            .classes("w-full")
            .props("outlined")
        )

        with ui.row().classes("w-full gap-2 mt-1"):
            ui.button("Cancelar", on_click=dialog.close).classes("flex-1").props(
                "outline color=grey-7"
            )

            def confirm():
                chosen_name = (name_field.value or "").strip()
                if not chosen_name:
                    show_error("El nombre no puede estar vacío")
                    return
                user_id = auth.current_user_id()
                if user_id is None:
                    dialog.close()
                    ui.navigate.to("/login")
                    return
                dialog.close()
                _do_add(chosen_name, cat_select.value, user_id, name_input, on_added)

            ui.button("Agregar", on_click=confirm).classes("flex-1").props("color=primary")

    dialog.open()


def _category_order(category: str) -> tuple[int, str]:
    """Categories in the CATEGORIES order (roughly a walk through the store), unknown ones last."""
    position = CATEGORIES.index(category) if category in CATEGORIES else len(CATEGORIES)
    return position, category


def _render_active_list(catalog: dict, refresh):
    """Pending items grouped by category, one card per category."""
    with get_db() as db:
        active = get_active_list(db)
        active_data = [
            (entry.id, entry.item.name, entry.item.category, entry.added_by.name, entry.added_by_user_id)
            for entry in active
        ]
    catalog["on_list"] = {name.lower() for _, name, _, _, _ in active_data}

    if not active_data:
        empty_state("shopping_basket", "Tu lista está vacía", "Agrega un artículo arriba para comenzar")
        return

    count = len(active_data)
    ui.label(f"{count} artículo{'s' if count != 1 else ''} por comprar").classes(
        "text-sm text-muted px-1 mt-1"
    )

    by_cat: dict[str, list] = {}
    for entry_id, name, category, added_by, added_by_id in active_data:
        by_cat.setdefault(category, []).append((entry_id, name, added_by, added_by_id))

    for category in sorted(by_cat.keys(), key=_category_order):
        with ui.card().classes("w-full p-0 gap-0 overflow-hidden"):
            with ui.row().classes("w-full items-center gap-2 px-4 pt-3 pb-1 no-wrap"):
                ui.icon(CATEGORY_ICONS.get(category, "category"), size="18px").classes("text-primary")
                ui.label(category).classes("text-sm font-semibold flex-1")
                ui.label(str(len(by_cat[category]))).classes("text-xs text-muted")
            for entry_id, name, added_by, added_by_id in by_cat[category]:
                _render_grocery_row(entry_id, name, added_by, added_by_id, refresh)


def _render_grocery_row(entry_id: int, name: str, added_by: str, added_by_id: int, refresh):
    """One item: tap the circle or the name to mark it as bought."""
    with ui.element("div").classes("hogar-row"):
        ui.button(
            icon="radio_button_unchecked",
            on_click=lambda: _on_purchased(entry_id, name, refresh),
        ).props("flat round color=primary size=lg padding='6px' aria-label='Marcar como comprado'")

        with ui.column().classes("gap-0 flex-1 min-w-0 cursor-pointer").on(
            "click", lambda: _on_purchased(entry_id, name, refresh)
        ):
            ui.label(name).classes("font-medium")
            ui.label(f"agregado por {added_by}").classes("text-xs text-muted")

        with ui.button(icon="more_vert").props("flat round dense color=grey-7"):
            with ui.menu():
                ui.menu_item(
                    "Quitar de la lista (no se compró)",
                    on_click=lambda: _on_removed(entry_id, name, added_by_id, refresh),
                ).props("dense")


def _on_purchased(entry_id: int, name: str, refresh):
    with get_db() as db:
        mark_as_purchased(db, entry_id)
    refresh()
    undo_snackbar(f"«{name}» comprado", lambda: _undo_purchase(entry_id, refresh))


def _undo_purchase(entry_id: int, refresh):
    with get_db() as db:
        undo_purchase(db, entry_id)
    refresh()


def _on_removed(entry_id: int, name: str, added_by_id: int, refresh):
    with get_db() as db:
        remove_from_active_list(db, entry_id)
    refresh()

    def put_back():
        # Re-adding by name finds the catalog item, so its category is kept.
        with get_db() as db:
            add_to_active_list(db, item_name=name, user_id=added_by_id)
        refresh()

    undo_snackbar(f"«{name}» quitado de la lista", put_back)
