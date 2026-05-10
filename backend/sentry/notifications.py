"""Cross-platform desktop notifications.

A single ``notify(title, body)`` function picks the right backend per OS:
``win11toast`` for the rich Windows experience, ``notifypy`` everywhere
else. Callers never need to branch on platform.
"""

from __future__ import annotations

import platform
import threading

from .config import ASSETS_DIR

LOGO_PATH = ASSETS_DIR / "sentry_logo.png"
SOUND_PATH = ASSETS_DIR / "notification_sound.wav"


def _windows_notify(title: str, body: str) -> bool:
    try:
        from win11toast import toast
    except ImportError:
        return False

    args: dict[str, str] = {"title": title, "body": body, "app_id": "Sentry"}
    if LOGO_PATH.exists():
        args["icon"] = str(LOGO_PATH)
    if SOUND_PATH.exists():
        args["audio"] = str(SOUND_PATH)

    threading.Thread(target=lambda: toast(**args), daemon=True).start()
    return True


def _portable_notify(title: str, body: str) -> bool:
    try:
        from notifypy import Notify
    except ImportError:
        return False

    n = Notify()
    n.title = title
    n.message = body
    n.application_name = "Sentry"
    if LOGO_PATH.exists():
        n.icon = str(LOGO_PATH)
    if SOUND_PATH.exists():
        n.audio = str(SOUND_PATH)
    n.send(block=False)
    return True


def notify(title: str, body: str) -> bool:
    """Send a desktop notification. Returns True if delivered."""
    if platform.system() == "Windows" and _windows_notify(title, body):
        return True
    return _portable_notify(title, body)
