"""Pure-math tests for the CVA calculation. No MediaPipe required."""

from __future__ import annotations

import math
from dataclasses import dataclass

from sentry.posture import calculate_cva


@dataclass
class L:
    x: float
    y: float
    z: float


def _scaffold() -> list[L]:
    return [L(0.0, 0.0, 0.0) for _ in range(33)]


def test_cva_perfectly_upright_is_90_degrees() -> None:
    lms = _scaffold()
    # Shoulders at origin level
    lms[11] = L(-0.2, 0.0, 0.0)
    lms[12] = L(0.2, 0.0, 0.0)
    # Ears 0.20 m above the shoulders (negative Y in MediaPipe world space)
    lms[7] = L(-0.1, -0.20, 0.0)
    lms[8] = L(0.1, -0.20, 0.0)
    assert math.isclose(calculate_cva(lms), 90.0, abs_tol=0.5)


def test_cva_decreases_with_forward_lean() -> None:
    lms = _scaffold()
    lms[11] = L(-0.2, 0.0, 0.0)
    lms[12] = L(0.2, 0.0, 0.0)
    # Same vertical but pushed forward in Z — head juts out
    lms[7] = L(-0.1, -0.20, 0.20)
    lms[8] = L(0.1, -0.20, 0.20)
    cva = calculate_cva(lms)
    assert 40.0 < cva < 50.0  # ~45° when dy == dxz


def test_cva_zero_when_head_is_level_with_shoulders() -> None:
    lms = _scaffold()
    lms[11] = L(-0.2, 0.0, 0.0)
    lms[12] = L(0.2, 0.0, 0.0)
    lms[7] = L(-0.1, 0.0, 0.20)
    lms[8] = L(0.1, 0.0, 0.20)
    assert abs(calculate_cva(lms)) < 0.5
