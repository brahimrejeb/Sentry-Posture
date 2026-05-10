"""Test fixtures.

We add ``backend/`` to ``sys.path`` so tests can ``import sentry...`` without
installing the package, and provide a fake MediaPipe model file so the
detector can be constructed in CI environments without a network.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Use an isolated SENTRY_HOME so tests never touch a developer's real config.
TEST_HOME = ROOT / "backend" / "tests" / ".sentry-test-home"
os.environ["SENTRY_HOME"] = str(TEST_HOME)
TEST_HOME.mkdir(parents=True, exist_ok=True)
(TEST_HOME / "models").mkdir(parents=True, exist_ok=True)
