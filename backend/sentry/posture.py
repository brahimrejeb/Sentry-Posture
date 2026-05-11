"""Pose landmarker wrapper and craniovertebral angle (CVA) maths.

We use MediaPipe's ``PoseLandmarker`` configured for up to three poses so
we can keep tracking the right person when others briefly enter the frame.
The CVA is computed from world-space (3D) landmarks so it's invariant to
how close the user sits to the camera.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

from .config import MODEL_REGISTRY, model_path

# MediaPipe Pose landmark indices (https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker).
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24

NUM_POSES = 3


@dataclass
class PoseObservation:
    """A single detected person in a single frame."""

    cva: float
    shoulder_width: float
    torso_length: float
    image_landmarks: list[Any]
    world_landmarks: list[Any]


def _midpoint(a: Any, b: Any) -> tuple[float, float, float]:
    return ((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2)


def calculate_cva(world_landmarks: list[Any]) -> float:
    """3D Craniovertebral Angle in degrees.

    CVA is the angle between the line from C7 (shoulder midpoint) to the
    tragus (ear midpoint) and a horizontal reference. A smaller angle
    means more forward head posture.
    """
    c7 = _midpoint(world_landmarks[LEFT_SHOULDER], world_landmarks[RIGHT_SHOULDER])
    tragus = _midpoint(world_landmarks[LEFT_EAR], world_landmarks[RIGHT_EAR])
    # MediaPipe's world Y axis points down, so an upward vector has dy>0.
    dy = c7[1] - tragus[1]
    dxz = math.hypot(tragus[0] - c7[0], tragus[2] - c7[2])
    return math.degrees(math.atan2(dy, dxz))


def _segment_length(a: Any, b: Any) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


class PostureDetector:
    """Wraps MediaPipe Pose Landmarker and exposes per-frame observations."""

    def __init__(self, model_level: str = "full") -> None:
        self.current_model = model_level
        self.detector: mp_vision.PoseLandmarker | None = None
        self._initialize(model_level)

    def _initialize(self, model_level: str) -> None:
        if model_level not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model level: {model_level}")
        path = model_path(model_level)
        if not path.exists():
            raise FileNotFoundError(
                f"Model file missing at {path}. Run `python run.py` to download it."
            )
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(path)),
            num_poses=NUM_POSES,
            output_segmentation_masks=False,
        )
        if self.detector is not None:
            self.detector.close()
        self.detector = mp_vision.PoseLandmarker.create_from_options(options)
        self.current_model = model_level

    def set_model(self, model_level: str) -> None:
        if model_level != self.current_model:
            self._initialize(model_level)

    def detect(self, frame_rgb: np.ndarray) -> list[PoseObservation]:
        assert self.detector is not None
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        try:
            result = self.detector.detect(mp_image)
        except Exception:
            return []

        observations: list[PoseObservation] = []
        worlds = result.pose_world_landmarks or []
        images = result.pose_landmarks or []
        for world_lms, image_lms in zip(worlds, images, strict=False):
            try:
                cva = calculate_cva(world_lms)
                sw = _segment_length(world_lms[LEFT_SHOULDER], world_lms[RIGHT_SHOULDER])
                tl = _segment_length(
                    _AvgLandmark(world_lms[LEFT_SHOULDER], world_lms[RIGHT_SHOULDER]),
                    _AvgLandmark(world_lms[LEFT_HIP], world_lms[RIGHT_HIP]),
                )
            except (IndexError, AttributeError):
                continue
            observations.append(
                PoseObservation(
                    cva=cva,
                    shoulder_width=sw,
                    torso_length=tl,
                    image_landmarks=image_lms,
                    world_landmarks=world_lms,
                )
            )
        return observations


class _AvgLandmark:
    """Tiny helper so ``_segment_length`` can take a virtual midpoint."""

    __slots__ = ("x", "y", "z")

    def __init__(self, a: Any, b: Any) -> None:
        self.x = (a.x + b.x) / 2
        self.y = (a.y + b.y) / 2
        self.z = (a.z + b.z) / 2


def draw_debug(
    frame_bgr: np.ndarray,
    image_landmarks: list[Any] | None,
    *,
    tracker_state: Any = None,
    is_slouching: bool = False,
) -> np.ndarray:
    """Draw the C7→tragus vector, a horizontal reference, and the tracker state.

    ``tracker_state`` is a :class:`~sentry.tracker.TrackerState` (passed as
    ``Any`` to avoid a circular import). The overlay's colour and label
    follow the same source of truth the StatusCard reads, so the camera
    feed never disagrees with the UI.
    """
    h, w = frame_bgr.shape[:2]
    state_str = getattr(tracker_state, "value", str(tracker_state) if tracker_state else "idle")

    # Pick the label and color the same way the UI status reads them.
    # BGR: red = slouching, green = locked + good, yellow = searching/idle,
    # gray = paused (camera-tracked person away).
    if state_str == "locked":
        if is_slouching:
            color = (0, 0, 220)
            label = "SLOUCHING"
        else:
            color = (0, 200, 0)
            label = "LOCKED"
    elif state_str == "paused":
        color = (160, 160, 160)
        label = "PAUSED (away)"
    elif state_str == "searching":
        color = (0, 200, 220)
        label = "SEARCHING"
    else:
        color = (180, 180, 180)
        label = "IDLE"

    cv2.putText(frame_bgr, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    if not image_landmarks:
        return frame_bgr

    l_sh, r_sh = image_landmarks[LEFT_SHOULDER], image_landmarks[RIGHT_SHOULDER]
    l_ear, r_ear = image_landmarks[LEFT_EAR], image_landmarks[RIGHT_EAR]
    c7 = (int((l_sh.x + r_sh.x) / 2 * w), int((l_sh.y + r_sh.y) / 2 * h))
    tragus = (int((l_ear.x + r_ear.x) / 2 * w), int((l_ear.y + r_ear.y) / 2 * h))

    cv2.line(frame_bgr, c7, tragus, color, 3)
    cv2.line(frame_bgr, c7, (c7[0] - 60, c7[1]), (255, 255, 255), 2)
    cv2.circle(frame_bgr, c7, 6, (255, 0, 0), -1)
    cv2.circle(frame_bgr, tragus, 6, (255, 0, 0), -1)
    return frame_bgr
