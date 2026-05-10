"""CLI shim so ``run.py`` can invoke model downloads inside the venv."""

from __future__ import annotations

import argparse

from .config import DEFAULT_MODEL, MODEL_REGISTRY
from .models_download import ensure_model


def main() -> int:
    parser = argparse.ArgumentParser(prog="sentry.models_download")
    parser.add_argument("level", nargs="?", default=DEFAULT_MODEL, choices=list(MODEL_REGISTRY))
    args = parser.parse_args()
    path = ensure_model(args.level)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
