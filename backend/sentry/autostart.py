"""Per-user, no-elevation auto-start at login.

Three platform branches:

* **Windows** — registry key under
  ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``.
* **macOS** — LaunchAgent plist under ``~/Library/LaunchAgents``.
* **Linux** — XDG ``~/.config/autostart/sentry.desktop``.

We register the installed entry-point script (``sentry-gui.exe`` on
Windows for a console-less launch, ``sentry`` on macOS/Linux). That
single executable is enough — it imports the package and starts the
backend without a fragile parent-child Python chain. Each call is
idempotent and runs without elevation.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import REPO_ROOT

APP_ID = "Sentry"
LAUNCH_ID = "com.sentry.posture"
ENTRY_FLAGS = ["--no-browser", "--autostarted"]


@dataclass
class AutostartInfo:
    enabled: bool
    supported: bool
    command: str | None
    target: str | None
    platform: str


# ---------------------------------------------------------------------------
# Public API
def describe() -> AutostartInfo:
    impl = _impl()
    if impl is None:
        return AutostartInfo(False, False, None, None, platform.system())
    enabled = impl.is_enabled()
    cmd, target = impl.preview()
    return AutostartInfo(enabled, True, cmd, target, platform.system())


def is_enabled() -> bool:
    impl = _impl()
    return bool(impl and impl.is_enabled())


def enable() -> None:
    impl = _impl()
    if impl is None:
        raise RuntimeError(f"Auto-start is not supported on {platform.system()}.")
    impl.enable()


def disable() -> None:
    impl = _impl()
    if impl is None:
        return
    impl.disable()


# ---------------------------------------------------------------------------
# Helpers
def _entry_executable() -> Path:
    """Locate the installed Sentry entry point.

    On Windows we prefer ``sentry-gui.exe`` (console-less); on macOS/Linux
    the ``sentry`` console script does the same job. Both are produced by
    ``uv sync`` from the ``[project.scripts]`` / ``[project.gui-scripts]``
    declarations in ``pyproject.toml``.

    Falls back to a python-module form if the entry-point binary is
    missing — that should only happen if the user hasn't run
    ``python run.py`` yet.
    """
    venv = REPO_ROOT / ".venv"
    if platform.system() == "Windows":
        for name in ("sentry-gui.exe", "sentry.exe"):
            candidate = venv / "Scripts" / name
            if candidate.exists():
                return candidate
    else:
        candidate = venv / "bin" / "sentry"
        if candidate.exists():
            return candidate
    # Fall back to whatever ``sentry`` resolves to on PATH (rare).
    found = shutil.which("sentry-gui") or shutil.which("sentry")
    if found:
        return Path(found)
    return Path(sys.executable)


def _entry_command() -> list[str]:
    exe = _entry_executable()
    if exe.suffix.lower() == ".exe" or exe.name in {"sentry", "sentry-gui"}:
        return [str(exe), *ENTRY_FLAGS]
    # Fallback: invoke as ``python -m sentry`` from the repo root.
    return [str(exe), "-m", "sentry", *ENTRY_FLAGS]


def _quoted(parts: list[str]) -> str:
    """Join an argv into a single shell-friendly string."""
    out: list[str] = []
    for part in parts:
        if any(c.isspace() for c in part) or part == "":
            out.append(f'"{part}"')
        else:
            out.append(part)
    return " ".join(out)


def _impl():  # type: ignore[no-untyped-def]
    system = platform.system()
    if system == "Windows":
        return _WindowsAutostart()
    if system == "Darwin":
        return _MacAutostart()
    if system == "Linux":
        return _LinuxAutostart()
    return None


# ---------------------------------------------------------------------------
# Windows — registry
class _WindowsAutostart:
    KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def preview(self) -> tuple[str, str]:
        cmd = _quoted(_entry_command())
        return cmd, fr"HKCU\{self.KEY_PATH}\{APP_ID}"

    def is_enabled(self) -> bool:
        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY_PATH) as key:
                value, _ = winreg.QueryValueEx(key, APP_ID)
                return bool(value)
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def enable(self) -> None:
        import winreg  # type: ignore[import-not-found]

        cmd = _quoted(_entry_command())
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY_PATH) as key:
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, cmd)

    def disable(self) -> None:
        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError:
            return
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.KEY_PATH, 0, winreg.KEY_ALL_ACCESS
            ) as key:
                winreg.DeleteValue(key, APP_ID)
        except FileNotFoundError:
            return
        except OSError:
            return


# ---------------------------------------------------------------------------
# macOS — LaunchAgent
class _MacAutostart:
    @property
    def plist_path(self) -> Path:
        override = os.environ.get("SENTRY_LAUNCH_AGENT_DIR")
        base = Path(override) if override else Path.home() / "Library" / "LaunchAgents"
        return base / f"{LAUNCH_ID}.plist"

    def preview(self) -> tuple[str, str]:
        return _quoted(_entry_command()), str(self.plist_path)

    def is_enabled(self) -> bool:
        return self.plist_path.exists()

    def enable(self) -> None:
        argv = _entry_command()
        program_args = "\n".join(f"        <string>{_xml_escape(a)}</string>" for a in argv)
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>{LAUNCH_ID}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{_xml_escape(str(REPO_ROOT))}</string>
  </dict>
</plist>
"""
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        self.plist_path.write_text(body, encoding="utf-8")

    def disable(self) -> None:
        try:
            self.plist_path.unlink()
        except FileNotFoundError:
            return


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Linux — XDG autostart
class _LinuxAutostart:
    @property
    def desktop_path(self) -> Path:
        override = os.environ.get("SENTRY_AUTOSTART_DIR")
        base = (
            Path(override)
            if override
            else Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
            / "autostart"
        )
        return base / "sentry.desktop"

    def preview(self) -> tuple[str, str]:
        return _quoted(_entry_command()), str(self.desktop_path)

    def is_enabled(self) -> bool:
        return self.desktop_path.exists()

    def enable(self) -> None:
        cmd = _quoted(_entry_command())
        body = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_ID}\n"
            "Comment=Local, privacy-first posture monitor\n"
            f"Exec={cmd}\n"
            f"Path={REPO_ROOT}\n"
            "X-GNOME-Autostart-enabled=true\n"
            "Terminal=false\n"
        )
        self.desktop_path.parent.mkdir(parents=True, exist_ok=True)
        self.desktop_path.write_text(body, encoding="utf-8")

    def disable(self) -> None:
        try:
            self.desktop_path.unlink()
        except FileNotFoundError:
            return


__all__ = ["AutostartInfo", "describe", "disable", "enable", "is_enabled"]
