# Contributor setup

End users only need the [README](../README.md). This document is for people
hacking on Sentry.

## Requirements

- Python 3.10–3.12
- Node 18+ (only if you're touching the UI; end users get a pre-built bundle)

## Run with HMR

```bash
python run.py --dev
```

This installs Python deps, the MediaPipe model, npm packages, then starts:

- `uvicorn` on `http://127.0.0.1:47821` serving the API (or the next free port if it's busy).
- Vite dev server on `http://127.0.0.1:5173` with hot module reload.

The Vite config proxies `/api/*` to the FastAPI port, so the UI code can
use a single base URL in both modes.

## Project layout

```
sentry/
├─ run.py                    # one-step launcher (calls into backend/sentry)
├─ backend/sentry/           # the actual application package
│  ├─ api.py                 # FastAPI app + AppState
│  ├─ camera.py              # capture + device enumeration
│  ├─ config.py              # paths, model registry, UserSettings
│  ├─ models.py              # pydantic schemas
│  ├─ models_download.py     # first-run model fetch
│  ├─ notifications.py       # cross-platform notify(title, body)
│  ├─ posture.py             # MediaPipe wrapper, CVA math
│  ├─ tracker.py             # state machine + identity matching
│  └─ tray.py                # pystray icon
├─ backend/tests/            # pytest suite
├─ ui/                       # React + Vite frontend
└─ docs/                     # this folder
```

## Cache locations

- `~/.sentry/models/`  — downloaded MediaPipe `.task` files.
- `~/.sentry/config.json` — persisted user settings.

Override with `SENTRY_HOME=/some/path` to use an isolated cache (the test
suite does this automatically).

## Useful commands

```bash
make test       # pytest + vitest
make lint       # ruff + eslint
make build      # produce ui/dist/ for a release zip
```

## Debugging tips

- Toggle _Diagnostics → Show camera + landmarks_ in the UI to see the
  C7→tragus vector overlaid on the live feed.
- `python -m sentry --no-tray --no-browser` runs the backend in the
  foreground without side effects, which is convenient under a debugger.
- The state machine lives in `backend/sentry/tracker.py` and is fully
  unit-testable; reproduce edge cases there before spelunking through the
  monitor loop.
