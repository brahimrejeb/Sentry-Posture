"""System tray icon. Isolated so headless test environments can import the
rest of the package without pystray side effects."""

from __future__ import annotations

import threading
import webbrowser
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from .config import ASSETS_DIR

LOGO_PATH = ASSETS_DIR / "sentry_logo.png"


def _make_icon_image() -> Image.Image:
    if LOGO_PATH.exists():
        return Image.open(LOGO_PATH)
    image = Image.new("RGB", (64, 64), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill="#7DB57F")
    return image


def run_tray(open_url: str, on_quit: Callable[[], None]) -> threading.Thread:
    """Start the tray on a background thread. Returns the thread."""

    def _quit(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        icon.stop()
        on_quit()

    def _open(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        webbrowser.open(open_url)

    icon = pystray.Icon(
        "Sentry",
        _make_icon_image(),
        "Sentry — Posture Monitor",
        menu=pystray.Menu(
            pystray.MenuItem("Open dashboard", _open, default=True),
            pystray.MenuItem("Quit Sentry", _quit),
        ),
    )

    thread = threading.Thread(target=icon.run, daemon=True, name="sentry-tray")
    thread.start()
    return thread
