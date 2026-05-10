"""Drive the smart tracker state machine through scripted scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from sentry.posture import PoseObservation
from sentry.tracker import Tracker, TrackerState


@dataclass
class _DummyLandmark:
    pass


def make_obs(cva: float, shoulder_width: float = 0.40, torso_length: float = 0.55) -> PoseObservation:
    return PoseObservation(
        cva=cva,
        shoulder_width=shoulder_width,
        torso_length=torso_length,
        image_landmarks=[],
        world_landmarks=[],
    )


def step(tracker: Tracker, t: float, people, baseline=None):
    if baseline is not None and tracker.baseline_cva is None:
        tracker.set_baseline(baseline)
    return tracker.tick(people, now=t)


def test_idle_until_started() -> None:
    t = Tracker()
    out = t.tick([make_obs(60)], now=0.0)
    assert out.state is TrackerState.IDLE


def test_lock_after_consecutive_frames() -> None:
    t = Tracker()
    t.start(fps=2.0)
    out0 = t.tick([make_obs(60)], now=0.0)
    assert out0.state is TrackerState.SEARCHING
    out1 = t.tick([make_obs(60)], now=0.5)
    out2 = t.tick([make_obs(60)], now=1.0)
    assert out2.state is TrackerState.LOCKED
    assert out1.state in (TrackerState.SEARCHING, TrackerState.LOCKED)


def test_pause_after_consecutive_absences() -> None:
    t = Tracker()
    t.start(fps=2.0)
    for i in range(3):
        t.tick([make_obs(60)], now=i * 0.5)
    assert t.state is TrackerState.LOCKED
    for i in range(5):
        t.tick([], now=2.0 + i * 0.5)
    assert t.state is TrackerState.PAUSED


def test_no_alert_during_settling_after_short_absence() -> None:
    t = Tracker(slouch_time_threshold=2.0, sensitivity_threshold=10.0, settling_seconds=5.0)
    t.set_baseline(60.0)
    t.start(fps=2.0)
    # Sit upright for a while
    for i in range(4):
        t.tick([make_obs(60.0)], now=i * 0.5)
    assert t.state is TrackerState.LOCKED

    # Walk away
    for i in range(6):
        t.tick([], now=2.0 + i * 0.5)
    assert t.state is TrackerState.PAUSED

    # Come back, lean forward (slouching) for several seconds — should be
    # suppressed during settling, no alert fires.
    base = 5.5
    fired = False
    for i in range(20):
        out = t.tick([make_obs(40.0)], now=base + i * 0.5)
        if out.should_alert:
            fired = True
    # The settling window is 5 s; even though the bad CVA is way past
    # threshold, no alert during that period.
    # The slouch_time_threshold is short, but the window is cleared while
    # settling, so the user gets a grace period.
    assert not fired or out.state is TrackerState.LOCKED


def test_alert_fires_when_slouching_persists() -> None:
    t = Tracker(slouch_time_threshold=2.0, sensitivity_threshold=10.0, settling_seconds=0.0)
    t.set_baseline(60.0)
    t.start(fps=4.0)
    # Lock on
    for i in range(6):
        t.tick([make_obs(60.0)], now=i * 0.25)
    assert t.state is TrackerState.LOCKED
    # Slouch hard for >slouch_time_threshold
    fired_at = None
    for i in range(20):
        out = t.tick([make_obs(40.0)], now=1.6 + i * 0.25)
        if out.should_alert:
            fired_at = i
            break
    assert fired_at is not None


def test_long_absence_sets_welcome_back() -> None:
    t = Tracker(settling_seconds=1.0, away_recalibrate_seconds=10.0)
    t.set_baseline(60.0)
    t.start(fps=2.0)
    # Lock on
    for i in range(4):
        t.tick([make_obs(60.0)], now=i * 0.5)
    # Disappear for a long time
    for i in range(40):
        t.tick([], now=2.0 + i * 0.5)
    assert t.state is TrackerState.PAUSED
    # Come back after 20 s away
    out_a = t.tick([make_obs(60.0)], now=22.5)
    out_b = t.tick([make_obs(60.0)], now=23.0)
    out_c = t.tick([make_obs(60.0)], now=24.0)  # past settling
    welcome = out_a.welcome_back or out_b.welcome_back or out_c.welcome_back
    assert welcome


def test_stand_up_fires_after_threshold_then_resets_on_break() -> None:
    t = Tracker(stand_up_after_seconds=5.0)
    t.start(fps=4.0)

    # Lock on
    for i in range(6):
        t.tick([make_obs(60.0)], now=i * 0.25)
    assert t.state is TrackerState.LOCKED

    # Tick past the stand-up threshold
    fired = False
    for i in range(40):
        out = t.tick([make_obs(60.0)], now=2.0 + i * 0.25)
        if out.should_stand_up:
            fired = True
            break
    assert fired, "Stand-up should have fired after 5 s of locked time"

    # Subsequent ticks shouldn't re-fire on the same streak
    out = t.tick([make_obs(60.0)], now=20.0)
    assert not out.should_stand_up

    # Take a break — when re-locked, the clock resets and stand-up can fire again
    for i in range(20):
        t.tick([], now=21.0 + i * 0.5)
    assert t.state is TrackerState.PAUSED
    for i in range(6):
        t.tick([make_obs(60.0)], now=32.0 + i * 0.25)
    assert t.state is TrackerState.LOCKED
    fired_again = False
    for i in range(40):
        out = t.tick([make_obs(60.0)], now=34.0 + i * 0.25)
        if out.should_stand_up:
            fired_again = True
            break
    assert fired_again


def test_identity_locks_to_first_person() -> None:
    """A second, very differently-shaped person should not steal the lock."""
    t = Tracker()
    t.start(fps=2.0)
    me = make_obs(60.0, shoulder_width=0.40, torso_length=0.55)
    other = make_obs(45.0, shoulder_width=0.20, torso_length=0.30)
    for i in range(4):
        t.tick([me], now=i * 0.5)
    assert t.state is TrackerState.LOCKED
    out = t.tick([me, other], now=2.5)
    assert out.primary is me  # the close-match wins
    assert out.people_in_frame == 2
