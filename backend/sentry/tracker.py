"""Presence + identity state machine.

Wraps :class:`PostureDetector` and produces frame-by-frame decisions:

* which detected person is the *primary* one;
* what overall state the session is in (IDLE / SEARCHING / LOCKED / PAUSED);
* whether we should fire a slouch alert *now*.

The state machine is intentionally pure-Python and free of MediaPipe so it
can be unit-tested with synthetic inputs.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .posture import PoseObservation


class TrackerState(str, Enum):
    IDLE = "idle"
    SEARCHING = "searching"
    LOCKED = "locked"
    PAUSED = "paused"


# Tunables. Frame-rate-independent: durations are in seconds.
LOCK_AFTER_SECONDS = 1.0
PAUSE_AFTER_SECONDS = 2.0
SETTLING_SECONDS_DEFAULT = 5.0
AWAY_RECALIBRATE_DEFAULT = 60.0
ROLLING_MEDIAN_SECONDS = 1.0


@dataclass
class _Identity:
    shoulder_width: float
    torso_length: float

    def distance(self, other: PoseObservation) -> float:
        sw = self.shoulder_width or 1e-6
        tl = self.torso_length or 1e-6
        return abs(other.shoulder_width - self.shoulder_width) / sw + abs(
            other.torso_length - self.torso_length
        ) / tl


@dataclass
class TickResult:
    state: TrackerState
    primary: PoseObservation | None
    is_slouching: bool
    should_alert: bool
    should_stand_up: bool
    locked_streak_seconds: float
    people_in_frame: int
    deviation: float
    settling: bool
    welcome_back: bool = False


@dataclass
class _CvaSample:
    t: float
    cva: float


@dataclass
class Tracker:
    """A per-session smart tracker.

    Call :meth:`tick` once per processed frame with the list of people the
    detector found. The tracker handles state transitions, identity matching,
    rolling-median smoothing, and alert hysteresis.
    """

    sensitivity_threshold: float = 15.0
    slouch_time_threshold: float = 15.0
    alert_cooldown: float = 30.0
    settling_seconds: float = SETTLING_SECONDS_DEFAULT
    away_recalibrate_seconds: float = AWAY_RECALIBRATE_DEFAULT
    stand_up_after_seconds: float = 50 * 60.0

    state: TrackerState = TrackerState.IDLE
    baseline_cva: float | None = None

    _identity: _Identity | None = field(default=None, init=False, repr=False)
    _cva_window: deque[_CvaSample] = field(default_factory=deque, init=False, repr=False)
    _slouch_started_at: float | None = field(default=None, init=False)
    _last_upright_at: float | None = field(default=None, init=False)
    _consec_with_person: int = field(default=0, init=False)
    _consec_without_person: int = field(default=0, init=False)
    _last_person_seen: float | None = field(default=None, init=False)
    _last_alert_at: float | None = field(default=None, init=False)
    _settling_until: float | None = field(default=None, init=False)
    _pause_started_at: float | None = field(default=None, init=False)
    _expected_fps: float = field(default=2.0, init=False)
    _welcome_back_pending: bool = field(default=False, init=False)
    _locked_since: float | None = field(default=None, init=False)
    _stand_up_fired_for_streak: bool = field(default=False, init=False)

    # ------------------------------------------------------------------
    # Read-only views
    @property
    def is_settling(self) -> bool:
        return self._settling_until is not None and time.time() < self._settling_until

    @property
    def last_alert_at(self) -> float | None:
        return self._last_alert_at

    # ------------------------------------------------------------------
    # Lifecycle
    def start(self, fps: float = 2.0) -> None:
        self._expected_fps = max(fps, 0.5)
        self.state = TrackerState.SEARCHING
        self._reset_session_buffers()

    def stop(self) -> None:
        self.state = TrackerState.IDLE
        self.baseline_cva = None
        self._identity = None
        self._reset_session_buffers()

    def set_baseline(self, cva: float) -> None:
        self.baseline_cva = cva

    def _reset_session_buffers(self) -> None:
        self._cva_window.clear()
        self._slouch_started_at = None
        self._last_upright_at = None
        self._consec_with_person = 0
        self._consec_without_person = 0
        self._last_person_seen = None
        self._last_alert_at = None
        self._settling_until = None
        self._pause_started_at = None
        self._welcome_back_pending = False
        self._locked_since = None
        self._stand_up_fired_for_streak = False

    # ------------------------------------------------------------------
    # Per-frame entry point
    def tick(self, people: list[PoseObservation], now: float | None = None) -> TickResult:
        now = time.time() if now is None else now
        if self.state is TrackerState.IDLE:
            return TickResult(
                state=self.state,
                primary=None,
                is_slouching=False,
                should_alert=False,
                should_stand_up=False,
                locked_streak_seconds=0.0,
                people_in_frame=len(people),
                deviation=0.0,
                settling=False,
            )

        primary = self._select_primary(people)
        has_person = primary is not None

        lock_threshold_frames = max(1, int(LOCK_AFTER_SECONDS * self._expected_fps))
        pause_threshold_frames = max(1, int(PAUSE_AFTER_SECONDS * self._expected_fps))

        if has_person:
            self._consec_with_person += 1
            self._consec_without_person = 0
            self._last_person_seen = now
        else:
            self._consec_without_person += 1
            self._consec_with_person = 0

        # Drive transitions.
        if self.state in (TrackerState.SEARCHING, TrackerState.PAUSED):
            if has_person and self._consec_with_person >= lock_threshold_frames:
                self._enter_locked(primary, now)
        elif (
            self.state is TrackerState.LOCKED
            and not has_person
            and self._consec_without_person >= pause_threshold_frames
        ):
            self._enter_paused(now)

        # Compute slouch stats only while LOCKED.
        is_slouching = False
        deviation = 0.0
        should_alert = False
        should_stand_up = False
        settling = False
        welcome_back = False

        if self.state is TrackerState.LOCKED and primary is not None:
            smoothed = self._smoothed_cva(now, primary.cva)
            if self.baseline_cva is not None:
                deviation = self.baseline_cva - smoothed
                is_slouching = deviation > self.sensitivity_threshold

            settling = self._settling_until is not None and now < self._settling_until
            if settling:
                # Suppress alerts during the settling period. Reset the
                # streak so that any pre-pause slouch state is discarded.
                self._slouch_started_at = None
                self._last_upright_at = None
            else:
                self._update_slouch_streak(now, is_slouching)
                if self._should_alert(now):
                    should_alert = True
                    self._last_alert_at = now
                if self._should_stand_up(now):
                    should_stand_up = True
                    self._stand_up_fired_for_streak = True

            if self._welcome_back_pending and not settling:
                welcome_back = True
                self._welcome_back_pending = False

        return TickResult(
            state=self.state,
            primary=primary,
            is_slouching=is_slouching,
            should_alert=should_alert,
            should_stand_up=should_stand_up,
            locked_streak_seconds=self.locked_streak_seconds(now),
            people_in_frame=len(people),
            deviation=deviation,
            settling=settling,
            welcome_back=welcome_back,
        )

    def locked_streak_seconds(self, now: float | None = None) -> float:
        if self._locked_since is None:
            return 0.0
        now = time.time() if now is None else now
        return max(0.0, now - self._locked_since)

    def _should_stand_up(self, now: float) -> bool:
        if self._stand_up_fired_for_streak or self.stand_up_after_seconds <= 0:
            return False
        return self.locked_streak_seconds(now) >= self.stand_up_after_seconds

    # ------------------------------------------------------------------
    # Helpers
    def _select_primary(self, people: list[PoseObservation]) -> PoseObservation | None:
        if not people:
            return None
        if self._identity is None:
            # First glimpse — pick the person with the largest torso (closest
            # to camera). They become the locked subject when we transition.
            return max(people, key=lambda p: p.torso_length or 0.0)
        # Score each person against the locked identity and pick the closest.
        scored = sorted(people, key=lambda p: self._identity.distance(p))  # type: ignore[union-attr]
        best = scored[0]
        if self._identity.distance(best) < 0.5:  # generous threshold
            return best
        # Nobody resembles the locked person — treat as no primary.
        return None

    def _enter_locked(self, primary: PoseObservation | None, now: float) -> None:
        if primary is None:
            return
        away_for = (now - self._pause_started_at) if self._pause_started_at else 0.0
        previous = self.state
        self.state = TrackerState.LOCKED
        self._pause_started_at = None
        # A break (any PAUSED transition) resets the stand-up clock.
        self._locked_since = now
        self._stand_up_fired_for_streak = False

        # Lock identity on first entry; refresh shoulder/torso every lock so
        # natural posture changes don't drift the match.
        self._identity = _Identity(primary.shoulder_width, primary.torso_length)

        if previous is TrackerState.PAUSED:
            self._settling_until = now + self.settling_seconds
            self._cva_window.clear()
            self._slouch_started_at = None
            self._last_upright_at = None
            if away_for > self.away_recalibrate_seconds:
                # Long absence → ask the user to re-calibrate.
                self._welcome_back_pending = True

    def _enter_paused(self, now: float) -> None:
        self.state = TrackerState.PAUSED
        self._pause_started_at = now
        self._slouch_started_at = None
        self._last_upright_at = None
        self._locked_since = None

    def _smoothed_cva(self, now: float, cva: float) -> float:
        self._cva_window.append(_CvaSample(now, cva))
        cutoff = now - ROLLING_MEDIAN_SECONDS
        while self._cva_window and self._cva_window[0].t < cutoff:
            self._cva_window.popleft()
        return statistics.median(s.cva for s in self._cva_window)

    def _update_slouch_streak(self, now: float, is_slouching: bool) -> None:
        """Track the current run of bad-posture frames.

        We don't reset the streak on a single upright frame — pose detection
        is jittery, and a brief recovery shouldn't necessarily clear the
        clock. Only after ``streak_break_seconds`` of mostly-upright do we
        decide the user has actually corrected.
        """
        streak_break_seconds = max(2.0, self.slouch_time_threshold * 0.2)
        if is_slouching:
            self._last_upright_at = None
            if self._slouch_started_at is None:
                self._slouch_started_at = now
        else:
            if self._slouch_started_at is None:
                return
            if self._last_upright_at is None:
                self._last_upright_at = now
            elif now - self._last_upright_at >= streak_break_seconds:
                self._slouch_started_at = None
                self._last_upright_at = None

    def _should_alert(self, now: float) -> bool:
        if self._slouch_started_at is None:
            return False
        if now - self._slouch_started_at < self.slouch_time_threshold:
            return False
        return not (
            self._last_alert_at is not None
            and now - self._last_alert_at < self.alert_cooldown
        )
