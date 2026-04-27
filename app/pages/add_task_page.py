"""
Add new task — form with a dynamic frequency selector.

The fields shown change based on the chosen frequency type.
This is a great example of NiceGUI's reactive UI pattern.
"""
from datetime import date
from nicegui import ui
from app.database import get_db
from app.ui_helpers import mobile_layout, show_success, show_error
from app.services.task_service import create_task


WEEKDAYS = [
    ("Lunes", 0), ("Martes", 1), ("Miércoles", 2),
    ("Jueves", 3), ("Viernes", 4), ("Sábado", 5), ("Domingo", 6),
]

FREQUENCY_OPTIONS = {
    "once": "Una sola vez (fecha específica)",
    "daily": "Diario",
    "weekly": "Semanal (día específico)",
    "specific_days": "Días específicos de la semana",
    "monthly": "Mensual (día específico)",
    "weekly_any": "Semanal (cualquier día)",
    "monthly_any": "Mensual (cualquier día)",
    "bimonthly_any": "Bimestral (cualquier día)",
    "every_x_days": "Cada X días",
}


def render():
    with mobile_layout("Nueva tarea", active_tab="tasks"):
        # State holders for form values
        state = {
            "name": "",
            "description": "",
            "frequency_type": "daily",
            # type-specific fields:
            "once_date": date.today().isoformat(),
            "weekly_day": 0,
            "specific_days": [],
            "monthly_day": 1,
            "x_days": 7,
        }

        with ui.card().classes("w-full p-4 gap-3"):
            name_input = ui.input("Nombre de la tarea").classes("w-full").props("outlined")
            name_input.bind_value(state, "name")

            desc_input = ui.textarea("Descripción (opcional)").classes("w-full").props(
                "outlined autogrow"
            )
            desc_input.bind_value(state, "description")

            ui.label("Frecuencia").classes("text-sm text-gray-500 mt-2")
            freq_select = (
                ui.select(FREQUENCY_OPTIONS, value="daily")
                .classes("w-full")
                .props("outlined")
            )
            freq_select.bind_value(state, "frequency_type")

            # The dynamic section — clears and re-renders when frequency_type changes
            dynamic_section = ui.column().classes("w-full gap-2")

            def render_dynamic():
                dynamic_section.clear()
                ftype = state["frequency_type"]
                with dynamic_section:
                    if ftype == "once":
                        date_input = (
                            ui.input("Fecha", value=state["once_date"])
                            .classes("w-full")
                            .props("outlined type=date")
                        )
                        date_input.bind_value(state, "once_date")

                    elif ftype == "daily":
                        ui.label("Se agregará a la lista todos los días.").classes(
                            "text-sm text-gray-500"
                        )

                    elif ftype == "weekly":
                        weekday_select = (
                            ui.select({i: name for name, i in WEEKDAYS}, value=0)
                            .classes("w-full")
                            .props("outlined label='Día de la semana'")
                        )
                        weekday_select.bind_value(state, "weekly_day")

                    elif ftype == "specific_days":
                        ui.label("Elige los días").classes("text-sm text-gray-500")
                        with ui.row().classes("flex-wrap gap-2"):
                            for label, idx in WEEKDAYS:
                                _day_chip(label, idx, state)
                    
                    elif ftype == "monthly":
                        day_select = (
                            ui.select(
                                {i: str(i) for i in range(1, 32)},
                                value=1,
                                label="Día del mes",
                            )
                            .classes("w-full")
                            .props("outlined")
                        )
                        day_select.bind_value(state, "monthly_day")

                    elif ftype == "weekly_any":
                        ui.label("Aparece cada día hasta completarse en la semana.").classes(
                            "text-sm text-gray-500"
                        )

                    elif ftype == "monthly_any":
                        ui.label("Aparece cada día hasta completarse en el mes.").classes(
                            "text-sm text-gray-500"
                        )

                    elif ftype == "bimonthly_any":
                        ui.label("Aparece cada día hasta completarse en el bimestre (cada 2 meses).").classes(
                            "text-sm text-gray-500"
                        )

                    elif ftype == "every_x_days":
                        days_input = (
                            ui.number("Cada cuántos días", value=state["x_days"], min=1, max=365)
                            .classes("w-full")
                            .props("outlined")
                        )
                        days_input.bind_value(state, "x_days")
                        ui.label(
                            "Reaparece exactamente ese número de días después de la última vez completada."
                        ).classes("text-sm text-gray-500")

            render_dynamic()
            freq_select.on_value_change(lambda _: render_dynamic())

        with ui.row().classes("w-full gap-2 mt-2"):
            ui.button("Cancelar", on_click=lambda: ui.navigate.to("/tasks")).classes(
                "flex-1"
            ).props("outline color=grey")
            ui.button("Guardar", on_click=lambda: _save(state)).classes("flex-1").props(
                "color=primary"
            )


def _day_chip(label: str, idx: int, state: dict):
    """Toggleable day chip for the 'specific days' picker."""
    chip = ui.chip(label, removable=False).props("clickable")

    def update_color():
        if idx in state["specific_days"]:
            chip.props("color=primary text-color=white")
        else:
            chip.props("color=grey-3 text-color=grey-8")

    update_color()

    def toggle():
        if idx in state["specific_days"]:
            state["specific_days"].remove(idx)
        else:
            state["specific_days"].append(idx)
        update_color()

    chip.on("click", toggle)


def _save(state: dict):
    name = state["name"].strip()
    if not name:
        show_error("El nombre de la tarea es obligatorio")
        return

    ftype = state["frequency_type"]
    config = {}

    if ftype == "once":
        config = {"date": state["once_date"]}
    elif ftype == "weekly":
        config = {"weekday": int(state["weekly_day"])}
    elif ftype == "specific_days":
        if not state["specific_days"]:
            show_error("Selecciona al menos un día")
            return
        config = {"weekdays": sorted(state["specific_days"])}
    elif ftype == "monthly":
        config = {"day": int(state["monthly_day"])}
    elif ftype == "every_x_days":
        x = int(state.get("x_days") or 7)
        if x < 1:
            show_error("El número de días debe ser al menos 1")
            return
        config = {"days": x}

    with get_db() as db:
        create_task(
            db,
            name=name,
            description=state["description"],
            frequency_type=ftype,
            frequency_config=config,
        )
    show_success(f"¡Tarea '{name}' creada!")
    ui.navigate.to("/tasks")