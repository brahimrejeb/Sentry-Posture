"""``python -m sentry`` — boot the API server, optional tray, and open browser."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from datetime import datetime

import uvicorn

from .api import create_app
from .config import DEFAULT_PORT, SENTRY_HOME, UI_DIST_DIR, RuntimeConfig
from .models_download import ensure_model

LOG_PATH = SENTRY_HOME / "sentry.log"
PORT_FILE = SENTRY_HOME / "runtime.port"
MAX_PORT_PROBE = 50


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sentry")
    parser.add_argument("--dev", action="store_true", help="Enable dev mode (CORS for Vite at :5173)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-tray", action="store_true", help="Don't start the system-tray icon"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't auto-open the browser"
    )
    parser.add_argument(
        "--autostarted",
        action="store_true",
        help="Set when invoked by the OS auto-start; redirects logs to a file.",
    )
    return parser.parse_args(argv)


def _redirect_stdio_to_log() -> None:
    """Redirect stdout/stderr to ``~/.sentry/sentry.log`` for windowless runs.

    When the OS launches us at login through ``sentry-gui.exe`` /
    LaunchAgent / .desktop, there's no console attached. Without this,
    a startup error (e.g., port already bound) would vanish silently.
    """
    SENTRY_HOME.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", buffering=1, encoding="utf-8", errors="replace")  # noqa: SIM115
    log.write(f"\n--- Sentry boot {datetime.now().isoformat(timespec='seconds')} ---\n")
    sys.stdout = log
    sys.stderr = log
    try:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    except (OSError, AttributeError):
        pass


def _is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _pick_free_port(host: str, requested: int) -> int:
    """Return ``requested`` if free, otherwise the next free port within
    ``MAX_PORT_PROBE`` slots upward."""
    for offset in range(MAX_PORT_PROBE):
        candidate = requested + offset
        if _is_port_free(host, candidate):
            return candidate
    raise RuntimeError(
        f"No free port found between {requested} and {requested + MAX_PORT_PROBE - 1}."
    )


def _print_running_banner(url: str) -> None:
    bar = "─" * (len(url) + 24)
    print(bar)
    print(f"  Sentry is running — open {url}")
    print("  (or click the Sentry icon in your system tray)")
    print(bar, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.autostarted:
        _redirect_stdio_to_log()
        print(f"Working dir: {os.getcwd()}")

    actual_port = _pick_free_port(args.host, args.port)
    if actual_port != args.port:
        print(
            f"Note: requested port {args.port} was busy, using {actual_port} instead.",
            file=sys.stderr,
        )

    config = RuntimeConfig(dev_mode=args.dev, host=args.host, port=actual_port)
    ensure_model(config.settings.model_level)

    app = create_app(config)
    state = app.state.sentry

    def _toggle_pause() -> None:
        if state.paused:
            state.resume_monitoring()
        else:
            state.pause_monitoring()

    server_url = f"http://{args.host}:{actual_port}/"
    if not args.dev and not UI_DIST_DIR.exists():
        print(
            "Warning: ui/dist not found. The API will run, but the dashboard\n"
            "is not built. Run `python run.py --dev` for HMR or `make build`\n"
            "to produce a static UI bundle.",
            file=sys.stderr,
        )

    # Persist the actually-bound port so wrappers (start.bat / start.sh)
    # can pick it up if they want to display a clickable URL.
    try:
        SENTRY_HOME.mkdir(parents=True, exist_ok=True)
        PORT_FILE.write_text(str(actual_port), encoding="utf-8")
    except OSError:
        pass

    tray_thread = None
    if not args.no_tray:
        try:
            from .tray import run_tray

            tray_thread = run_tray(
                server_url,
                on_quit=lambda: sys.exit(0),
                on_pause_toggle=_toggle_pause,
                is_paused=lambda: state.paused,
            )
        except Exception as exc:
            print(f"Could not start tray icon: {exc}", file=sys.stderr)

    if not args.no_browser and not args.dev:
        import threading
        import webbrowser

        def _open() -> None:
            time.sleep(0.8)
            webbrowser.open(server_url)

        threading.Thread(target=_open, daemon=True, name="sentry-browser-opener").start()

    _print_running_banner(server_url)
    uvicorn.run(app, host=args.host, port=actual_port, log_level="warning")
    if tray_thread is not None:
        tray_thread.join(timeout=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
