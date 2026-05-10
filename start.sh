#!/usr/bin/env bash
# Wrapper around run.py.
#
#   ./start.sh            -> background launch (terminal returns immediately,
#                            closing the shell does NOT kill the app).
#   ./start.sh foreground -> classic foreground run (Ctrl+C kills it).
set -euo pipefail
cd "$(dirname "$0")"

PY="python3"
if ! command -v python3 >/dev/null 2>&1; then
    PY="python"
fi

if [[ "${1-}" == "foreground" ]]; then
    shift
    exec "$PY" run.py "$@"
fi

mkdir -p "$HOME/.sentry"
nohup "$PY" run.py "$@" >>"$HOME/.sentry/sentry.log" 2>&1 &
PID=$!
echo
echo "Sentry is starting in the background (PID $PID)."
echo "Once it's up:"
echo "  - the dashboard opens in your default browser, OR"
echo "  - click the Sentry icon in your system tray,"
echo "  - or open http://127.0.0.1:47821/ manually."
echo "Logs:  $HOME/.sentry/sentry.log"
echo "Quit Sentry from the tray icon."
echo
