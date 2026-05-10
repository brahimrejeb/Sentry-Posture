# Contributing to Sentry

Thanks for your interest in helping out. Sentry is a small project so the
process is light.

## Local setup

You need Python 3.10–3.12 and (for UI work) Node 18+.

```bash
git clone https://github.com/<owner>/sentry.git
cd sentry
python run.py --dev
```

`run.py --dev` installs everything (`uv`, Python deps, npm packages, the
default MediaPipe model) and runs the backend together with the Vite dev
server (HMR enabled). The app opens on `http://127.0.0.1:5173` and the API
on `http://127.0.0.1:47821`.

## Running checks

```bash
make lint     # ruff
make test     # pytest + vitest
make build    # production UI build into ui/dist/
```

## Pull requests

- Keep PRs focused on a single concern; split unrelated changes.
- Run `make lint test` before opening the PR.
- Update `CHANGELOG.md` under the `## [Unreleased]` section.
- New behaviour needs a test. New API surface needs a docstring.

## Style

- Python: ruff handles formatting and linting (`make lint`). Type hints on
  public functions.
- TypeScript: keep components small. Avoid adding global state libraries —
  the backend is the source of truth, polled via `/api/status`.
- Comments explain *why*, not *what*. Skip them otherwise.

## Reporting bugs

Open an issue with: OS, Python version, what you did, what happened, and
what you expected. A short screen recording helps for UI bugs.
