"""
Shared "no network" guard for hermetic tests.

``socket.socket.connect`` is replaced by a function that records the attempt and refuses it. On Windows, ``socket.socketpair`` (used by
asyncio's event loop to wake itself up) is implemented with a loopback TCP connect; that internal call is the only
thing let through, so a test still fails on any real connection attempt.
"""
from __future__ import annotations

import socket
import sys
from typing import Any


class UnexpectedNetworkConnection(ConnectionRefusedError):
    """An OSError on purpose: the stdlib closes the half-open socket for OSError but leaks it for other exceptions.
    Tests assert on the recorded attempts, so swallowing the error in library code cannot hide the connection."""


def _called_from_socketpair() -> bool:
    frame = sys._getframe(2)
    for _ in range(4):
        if frame is None:
            return False
        if frame.f_code.co_name == "socketpair" and frame.f_code.co_filename.endswith(("socket.py", "windows_utils.py")):
            return True
        frame = frame.f_back
    return False


def block_network(monkeypatch) -> list[Any]:
    """Makes any outgoing connection raise AssertionError; returns the list of recorded attempts."""
    attempts: list[Any] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def no_connect(self, *a, **k):
        if _called_from_socketpair():
            return real_connect(self, *a, **k)
        attempts.append(a)
        raise UnexpectedNetworkConnection(f"unexpected network connection: {a}")

    def no_connect_ex(self, *a, **k):
        if _called_from_socketpair():
            return real_connect_ex(self, *a, **k)
        attempts.append(a)
        raise UnexpectedNetworkConnection(f"unexpected network connection: {a}")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", no_connect_ex)
    return attempts
