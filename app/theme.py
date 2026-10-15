"""
The app's look: colors, font, and the default style of buttons and cards.

Everything visual that is shared by all pages lives here and in
static/theme.css, so changing the look means editing one place.
Call `setup()` once before ui.run().
"""
from pathlib import Path

from nicegui import app, ui

CSS_FILE = Path(__file__).parent / "static" / "theme.css"

# Brand color: buttons, links, the current tab. Indigo keeps white text
# readable (contrast 6.3:1) and stands apart from the green/amber/red used
# for "done", "needs a photo" and "overdue".
PRIMARY = "#4f46e5"

# Page background; the header and the phone's status bar use it too.
BACKGROUND = "#f5f6fa"


def setup() -> None:
    """Apply the theme to every page."""
    app.colors(
        primary=PRIMARY,
        secondary="#0d9488",
        accent="#7c3aed",
        positive="#16a34a",
        negative="#dc2626",
        info="#0284c7",
        warning="#d97706",
    )
    ui.add_css(CSS_FILE, shared=True)

    # Sentence-case labels instead of ALL CAPS, and flat buttons
    # (the rounded corners are in theme.css).
    ui.button.default_props("no-caps unelevated")
