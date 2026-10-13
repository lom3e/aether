"""
Credential and network isolation for the test suite: the single implementation used by ``conftest.py`` (autouse
fixture) and by the tests that assert on the recorded attempts.

Policy
------
* Provider API keys are visible only to tests marked ``live_provider``.
* Ordinary tests (``integration`` included) may connect to loopback addresses only: the local servers their
  fixtures start. Every other destination is refused, and so is the local Ollama port (11434).
* ``@pytest.mark.ollama``                      -> additionally allows the local Ollama port (loopback only).
* ``@pytest.mark.external_network("host", ..)`` -> additionally allows exactly the listed hosts (connect and DNS).
  Without hosts the marker is a usage error: there is no blanket external-network opt-in except ``live_provider``.
* ``@pytest.mark.live_provider``               -> real keys and no network guard (explicit, used by live tests only,
  which also need their own opt-in environment variable).
* Strict mode (``network_policy.strict = True``) refuses even loopback; tests that must prove "nothing is contacted"
  use it.
* A refused attempt is recorded in ``network_attempts`` and the test FAILS at teardown even if the code under test
  swallowed the exception, unless it is marked ``network_block_expected`` (tests of the guard itself).
  ``integration`` grants neither credentials nor external network.

What the guard raises
---------------------
``UnexpectedNetworkConnection`` is an ``OSError`` (and a ``RuntimeError``). The standard library closes a half-open
socket only for ``OSError``; any other exception would leave it open and ``-W error`` would turn that into a
``ResourceWarning``. Library code that swallows ``OSError`` cannot hide the attempt: it is recorded in the returned list.

Limits (this is a safety net, not a security boundary)
-----------------------------------------------------
* It patches ``socket.socket.connect``/``connect_ex`` and ``socket.getaddrinfo`` in the test process only.
* asyncio's ``ProactorEventLoop`` on Windows connects with ``ConnectEx`` and bypasses ``socket.connect``; async network
  clients are therefore NOT covered there. UDP ``sendto``, raw sockets and ``socket.create_connection`` callers that
  resolve first are only covered through the DNS check.
* Child processes (the ``aether`` server, browsers, agents) are not covered: they only get an environment without
  provider keys. A deterministic test must never rely on a real external connection as its proof.
"""
from __future__ import annotations

import ipaddress
import socket
import sys
from dataclasses import dataclass, field
from typing import Any

PROVIDER_KEY_VARS = (
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)
OLLAMA_PORT = 11434
_LOCAL_NAMES = {"localhost", "localhost.localdomain", ""}


class UnexpectedNetworkConnection(ConnectionRefusedError, RuntimeError):
    """Refused by the test network guard (an OSError on purpose, see the module docstring)."""


class UnexpectedNameResolution(socket.gaierror, RuntimeError):
    """A DNS lookup for a non-local name was refused by the test network guard."""


def is_loopback_host(host: Any) -> bool:
    """True for literal loopback addresses and ``localhost``; False for anything else (no DNS is performed)."""
    if host is None:
        return False
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    text = str(host).strip().strip("[]").split("%", 1)[0].lower()
    if text in _LOCAL_NAMES:
        return True
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    if getattr(address, "ipv4_mapped", None) is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def _called_from_socketpair() -> bool:
    """On Windows ``socket.socketpair`` (asyncio's self-pipe) is a loopback TCP connect; only that is let through."""
    frame = sys._getframe(2)
    for _ in range(4):
        if frame is None:
            return False
        if frame.f_code.co_name == "socketpair" and frame.f_code.co_filename.endswith(("socket.py", "windows_utils.py")):
            return True
        frame = frame.f_back
    return False


@dataclass
class NetworkPolicy:
    """What the guard lets through for the current test; read at every call, so a fixture may tighten it."""

    allow_ollama: bool = False
    strict: bool = False  # refuse even loopback connections (DNS rules unchanged)
    extra_hosts: frozenset[str] = field(default_factory=frozenset)


def install_network_guard(
    monkeypatch, *, policy: NetworkPolicy | None = None, attempts: list[Any] | None = None
) -> list[Any]:
    """Refuses forbidden connections and DNS lookups for the current test; returns the list of refused attempts."""
    policy = NetworkPolicy() if policy is None else policy
    attempts = [] if attempts is None else attempts
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def host_allowed(host: Any) -> bool:
        return str(host).strip("[]").lower() in policy.extra_hosts

    def allowed(address: Any) -> bool:
        if not isinstance(address, tuple) or len(address) < 2:
            return True  # AF_UNIX path / other families: not a network destination
        host, port = address[0], address[1]
        if host_allowed(host):
            return True
        if policy.strict or not is_loopback_host(host):
            return False
        return policy.allow_ollama or port != OLLAMA_PORT

    def guarded_connect(self, address, *args, **kwargs):
        if not allowed(address) and not _called_from_socketpair():
            attempts.append(address)
            raise UnexpectedNetworkConnection(
                f"Ordinary tests must not open network connections (attempted {address}); mark the test "
                "live_provider, ollama or external_network('host') if it really needs one."
            )
        return real_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        if not allowed(address) and not _called_from_socketpair():
            attempts.append(address)
            raise UnexpectedNetworkConnection(f"unexpected network connection: {address}")
        return real_connect_ex(self, address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None and not is_loopback_host(host) and not host_allowed(host):
            text = host.decode("ascii", "ignore") if isinstance(host, bytes) else str(host)
            try:
                ipaddress.ip_address(text.strip("[]"))  # numeric literals need no lookup
            except ValueError:
                attempts.append(("getaddrinfo", text))
                raise UnexpectedNameResolution(f"unexpected DNS lookup for {text!r} in an ordinary test")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    return attempts
