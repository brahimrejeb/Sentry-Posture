# Changelog

All notable changes to this project will be documented in this file. The
format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - Initial public release

### Added
- One-step `python run.py` launcher that installs `uv`, syncs Python
  dependencies, downloads the default MediaPipe model, builds the UI if
  needed, and serves the app on a single port.
- Smart presence tracker with `IDLE`/`SEARCHING`/`LOCKED`/`PAUSED` states.
  No false slouch alerts after the user steps away and returns.
- Identity-locking primary-person selection so a passer-by does not break the
  baseline calibration.
- Cross-platform launcher shims (`start.sh`, `start.bat`) and contributor
  `Makefile`.
- GPL-3.0-or-later license, contributing guide, and code of conduct.

### Changed
- Backend reorganised into a `sentry` package under `backend/`.
- Calibration averages 30 frames over a short countdown rather than sampling
  a single noisy frame.
- Production builds serve the UI from FastAPI directly; no separate Vite
  process is required.

### Removed
- Bundled MediaPipe `.task` model files (~45 MB) — fetched on demand instead.
- Global custom cursor and unused frontend assets.
