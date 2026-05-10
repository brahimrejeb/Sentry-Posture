"""Download MediaPipe pose-landmarker model files on demand."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from .config import MODEL_DIR, MODEL_REGISTRY, has_model, model_path


def ensure_model(level: str, *, progress: bool = True) -> Path:
    """Make sure ``level`` exists locally; download if not. Returns the path."""
    if level not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model level: {level}")
    if has_model(level):
        return model_path(level)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    info = MODEL_REGISTRY[level]
    target = model_path(level)
    tmp = target.with_suffix(target.suffix + ".part")

    url = str(info["url"])
    size_mb = info["size_mb"]
    if progress:
        print(f"Downloading {level} model (~{size_mb} MB) from {url}", file=sys.stderr)

    def _hook(block: int, block_size: int, total_size: int) -> None:
        if not progress or total_size <= 0:
            return
        downloaded = block * block_size
        pct = min(100, downloaded * 100 // total_size)
        bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
        print(f"\r  [{bar}] {pct:3d}%", end="", file=sys.stderr, flush=True)

    try:
        urllib.request.urlretrieve(url, tmp, _hook)
    finally:
        if progress:
            print("", file=sys.stderr)
    tmp.replace(target)
    return target
