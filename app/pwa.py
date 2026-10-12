"""
Progressive Web App (PWA) support: users can install the app on their
phone's home screen, where it opens full screen like a native app.

  /manifest.webmanifest  the installed app's name, icons and colors
  /sw.js                 the service worker; it must be served from the
                         site's root to cover every page
  /pwa/...               icons, the offline page and the install banner
                         (files in app/static/pwa/)

Every page loads install.js, which registers the service worker and shows
the "install the app" banner.

Browsers only offer to install a site served over HTTPS (or from
localhost). See "HTTPS with Caddy" in the README.
"""
from pathlib import Path

from fastapi.responses import FileResponse
from nicegui import app, ui

STATIC_DIR = Path(__file__).parent / "static" / "pwa"

THEME_COLOR = "#5898d4"  # NiceGUI's default primary color (the header bar)

HEAD_HTML = f"""
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="{THEME_COLOR}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Hogar">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="/pwa/apple-touch-icon.png">
<link rel="stylesheet" href="/pwa/install.css">
<script src="/pwa/install.js" defer></script>
"""


def setup() -> None:
    """Serve the PWA files and add the PWA tags to every page. Call before ui.run()."""
    app.add_static_files("/pwa", STATIC_DIR)

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(STATIC_DIR / "manifest.webmanifest",
                            media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        # no-cache: browsers re-check it on every visit, so updates reach phones quickly
        return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache"})

    ui.add_head_html(HEAD_HTML, shared=True)
