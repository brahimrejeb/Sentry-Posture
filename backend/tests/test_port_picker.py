"""Tests for the port-availability scanner used at startup."""

from __future__ import annotations

import socket

from sentry.__main__ import _is_port_free, _pick_free_port


def test_pick_free_port_returns_requested_when_available() -> None:
    free = _pick_free_port("127.0.0.1", 0)
    # Port 0 means "let the OS pick"; the resulting port must actually be free.
    assert _is_port_free("127.0.0.1", free) is True


def test_pick_free_port_falls_back_when_busy() -> None:
    # Hold a port so it appears busy, then ask for it. We should get the
    # next one upward.
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    busy_port = holder.getsockname()[1]
    try:
        chosen = _pick_free_port("127.0.0.1", busy_port)
        assert chosen != busy_port
        assert chosen > busy_port
    finally:
        holder.close()
