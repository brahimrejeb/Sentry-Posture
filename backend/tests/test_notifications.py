"""Tests for the notification dispatcher's platform branching."""

from __future__ import annotations

from unittest.mock import patch

from sentry import notifications


def test_non_windows_uses_notifypy() -> None:
    with (
        patch("sentry.notifications.platform.system", return_value="Linux"),
        patch("sentry.notifications._portable_notify", return_value=True) as portable,
        patch("sentry.notifications._windows_notify", return_value=True) as win,
    ):
        assert notifications.notify("t", "b") is True
        portable.assert_called_once()
        win.assert_not_called()


def test_windows_prefers_win11toast_when_available() -> None:
    with (
        patch("sentry.notifications.platform.system", return_value="Windows"),
        patch("sentry.notifications._windows_notify", return_value=True) as win,
        patch("sentry.notifications._portable_notify", return_value=True) as portable,
    ):
        assert notifications.notify("t", "b") is True
        win.assert_called_once()
        portable.assert_not_called()


def test_windows_falls_back_when_toast_missing() -> None:
    with (
        patch("sentry.notifications.platform.system", return_value="Windows"),
        patch("sentry.notifications._windows_notify", return_value=False),
        patch("sentry.notifications._portable_notify", return_value=True) as portable,
    ):
        assert notifications.notify("t", "b") is True
        portable.assert_called_once()
