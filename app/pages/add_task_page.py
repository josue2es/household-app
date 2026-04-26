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
    ("Monday", 0), ("Tuesday", 1), ("Wednesday", 2),
    ("Thursday", 3), ("Friday", 4), ("Saturday", 5), ("Sunday", 6),
]

FREQUENCY_OPTIONS = {
    "once": "One-off (specific date)",
    "daily": "Daily",
    "weekly": "Weekly (one weekday)",
    "specific_days": "Specific days of the week",
    "monthly": "Monthly (specific day of month)",
}


def render():
    with mobile_layout("New Task", active_tab="tasks"):
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
        }

        with ui.card().classes("w-full p-4 gap-3"):
            name_input = ui.input("Task name").classes("w-full").props("outlined")
            name_input.bind_value(state, "name")

            desc_input = ui.textarea("Description (optional)").classes("w-full").props(
                "outlined autogrow"
            )
            desc_input.bind_value(state, "description")

            ui.label("Frequency").classes("text-sm text-gray-500 mt-2")
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
                            ui.input("Date", value=state["once_date"])
                            .classes("w-full")
                            .props("outlined type=date")
                        )
                        date_input.bind_value(state, "once_date")

                    elif ftype == "daily":
                        ui.label("Will be added to today's list every day.").classes(
                            "text-sm text-gray-500"
                        )

                    elif ftype == "weekly":
                        weekday_select = (
                            ui.select({i: name for name, i in WEEKDAYS}, value=0)
                            .classes("w-full")
                            .props("outlined label='Day of week'")
                        )
                        weekday_select.bind_value(state, "weekly_day")

                    elif ftype == "specific_days":
                        ui.label("Pick the days").classes("text-sm text-gray-500")
                        with ui.row().classes("flex-wrap gap-2"):
                            for label, idx in WEEKDAYS:
                                _day_chip(label, idx, state)
                    
                    elif ftype == "monthly":
                        day_select = (
                            ui.select(
                                {i: str(i) for i in range(1, 32)},
                                value=1,
                                label="Day of the month",
                            )
                            .classes("w-full")
                            .props("outlined")
                        )
                        day_select.bind_value(state, "monthly_day")

            render_dynamic()
            freq_select.on_value_change(lambda _: render_dynamic())

        with ui.row().classes("w-full gap-2 mt-2"):
            ui.button("Cancel", on_click=lambda: ui.navigate.to("/tasks")).classes(
                "flex-1"
            ).props("outline color=grey")
            ui.button("Save", on_click=lambda: _save(state)).classes("flex-1").props(
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
        show_error("Task name is required")
        return

    ftype = state["frequency_type"]
    config = {}

    if ftype == "once":
        config = {"date": state["once_date"]}
    elif ftype == "weekly":
        config = {"weekday": int(state["weekly_day"])}
    elif ftype == "specific_days":
        if not state["specific_days"]:
            show_error("Pick at least one day")
            return
        config = {"weekdays": sorted(state["specific_days"])}
    elif ftype == "monthly":
            config = {"day": int(state["monthly_day"])}
            
    with get_db() as db:
        create_task(
            db,
            name=name,
            description=state["description"],
            frequency_type=ftype,
            frequency_config=config,
        )
    show_success(f"Task '{name}' created!")
    ui.navigate.to("/tasks")