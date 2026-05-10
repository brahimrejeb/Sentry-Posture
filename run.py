"""One-step launcher.

Idempotent. Re-running is fast: only does work when something is actually
missing.

Pipeline:
    1. Verify Python version.
    2. Ensure ``uv`` is available; install via pip if not.
    3. Sync Python dependencies into a local ``.venv``.
    4. Ensure the default MediaPipe model is present in ``~/.sentry/models``.
    5. Make sure a UI bundle exists (build via npm if Node is available, or
       fall back to a pre-built ``ui/dist`` from a release zip).
    6. Boot the backend (``python -m sentry``) — this is the long-running step.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
UI_DIR = REPO_ROOT / "ui"
UI_DIST = UI_DIR / "dist"
VENV_DIR = REPO_ROOT / ".venv"
MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 12)


def _log(msg: str) -> None:
    print(f"[sentry] {msg}", flush=True)


def _check_python() -> None:
    cur = sys.version_info[:2]
    if cur < MIN_PYTHON or cur > MAX_PYTHON:
        sys.exit(
            f"Sentry needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}–"
            f"{MAX_PYTHON[0]}.{MAX_PYTHON[1]}. You're running {cur[0]}.{cur[1]}."
        )


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> int:
    pretty = " ".join(cmd)
    _log(f"$ {pretty}")
    proc = subprocess.run(cmd, cwd=cwd)
    if check and proc.returncode != 0:
        sys.exit(f"Command failed: {pretty}")
    return proc.returncode


def _ensure_uv() -> str:
    if _has("uv"):
        return "uv"
    _log("'uv' not found — installing via pip")
    _run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "uv"])
    if _has("uv"):
        return "uv"
    # Some user-base installs aren't on PATH; fall through to module form.
    return f"{sys.executable} -m uv"


def _venv_synced(extras: list[str]) -> bool:
    marker = VENV_DIR / ".sentry_synced"
    if not marker.exists():
        return False
    try:
        synced = set(marker.read_text(encoding="utf-8").split())
    except OSError:
        return False
    return set(extras).issubset(synced)


def _mark_synced(extras: list[str]) -> None:
    (VENV_DIR / ".sentry_synced").write_text(" ".join(extras), encoding="utf-8")


def _sync_python(extras: list[str]) -> None:
    if _venv_synced(extras):
        _log("Python deps already in sync.")
        return
    uv = _ensure_uv()
    parts = uv.split() + ["sync"]
    for extra in extras:
        parts += ["--extra", extra]
    _run(parts, cwd=REPO_ROOT)
    _mark_synced(extras)


def _venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _ensure_default_model() -> None:
    # Run inside the venv so we hit our pinned deps.
    _run(
        [str(_venv_python()), "-m", "sentry.models_download_cli"],
        cwd=BACKEND_DIR,
    )


def _ensure_ui(dev: bool) -> None:
    if dev:
        # Vite dev server installs deps lazily on its own.
        if not (UI_DIR / "node_modules").exists():
            if not _has("npm"):
                sys.exit(
                    "Dev mode needs Node + npm installed. See https://nodejs.org/"
                )
            _run(["npm", "install"], cwd=UI_DIR)
        return

    if UI_DIST.exists() and any(UI_DIST.iterdir()):
        return  # already built (release zip ship or prior build)

    if not _has("npm"):
        sys.exit(
            "ui/dist is missing and Node/npm are not installed.\n"
            "Either install Node ≥ 18 (https://nodejs.org/) or download the\n"
            "release zip, which ships a pre-built UI."
        )
    _run(["npm", "install"], cwd=UI_DIR)
    _run(["npm", "run", "build"], cwd=UI_DIR)


def _start_backend(dev: bool, no_tray: bool, no_browser: bool, port: int) -> int:
    cmd = [str(_venv_python()), "-m", "sentry"]
    if dev:
        cmd.append("--dev")
    if no_tray:
        cmd.append("--no-tray")
    if no_browser:
        cmd.append("--no-browser")
    cmd += ["--port", str(port)]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{BACKEND_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}"
    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    return proc.returncode


def _start_vite() -> subprocess.Popen[bytes]:
    return subprocess.Popen(["npm", "run", "dev"], cwd=UI_DIR, shell=platform.system() == "Windows")


def main() -> int:
    parser = argparse.ArgumentParser(prog="sentry-launcher")
    parser.add_argument("--dev", action="store_true", help="Run with Vite HMR (contributor mode)")
    parser.add_argument("--no-tray", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=47821)
    args = parser.parse_args()

    _check_python()
    _log(f"Python {sys.version_info.major}.{sys.version_info.minor} — repo at {REPO_ROOT}")

    extras = ["dev"] if args.dev else []
    _sync_python(extras)
    _ensure_default_model()
    _ensure_ui(args.dev)

    vite_proc: subprocess.Popen[bytes] | None = None
    if args.dev:
        _log("Starting Vite dev server on http://127.0.0.1:5173")
        vite_proc = _start_vite()

    try:
        return _start_backend(args.dev, args.no_tray, args.no_browser, args.port)
    finally:
        if vite_proc is not None and vite_proc.poll() is None:
            vite_proc.terminate()
            try:
                vite_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                vite_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
