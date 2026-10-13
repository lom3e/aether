"""
Tests of the test-suite protections themselves (credential and network isolation).

The real ``conftest.py`` and ``network_guard.py`` are copied next to a throw-away test module and run by a nested pytest
process, so that the fixture teardown (which fails a test that attempted forbidden network access, even if the code
under test swallowed the error) is observed for real. Nothing here touches an external host: every forbidden
destination is refused by the guard BEFORE any packet is sent, and the nested run never connects to Ollama.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent

INNER = '''
import os, socket
import pytest


def _swallowing_connect(addr):
    try:
        socket.create_connection(addr, timeout=1)
    except OSError:
        pass  # the code under test hides the failure on purpose


def test_swallowed_external_attempt_fails_at_teardown():
    _swallowing_connect(("93.184.216.34", 443))


@pytest.mark.network_block_expected
def test_swallowed_external_attempt_is_waived_when_expected(network_attempts):
    _swallowing_connect(("93.184.216.34", 443))
    assert network_attempts


def test_swallowed_dns_lookup_fails_at_teardown():
    try:
        socket.getaddrinfo("name-that-must-not-be-resolved.example", 80)
    except OSError:
        pass


def test_loopback_server_started_by_the_test_is_allowed():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.create_connection(server.getsockname(), timeout=2)
    client.close()
    server.close()


def test_strict_mode_refuses_even_loopback(network_policy):
    network_policy.strict = True
    _swallowing_connect(("127.0.0.1", 9))


@pytest.mark.network_block_expected
def test_strict_mode_records_the_loopback_attempt(network_policy, network_attempts):
    network_policy.strict = True
    _swallowing_connect(("127.0.0.1", 9))
    assert network_attempts == [("127.0.0.1", 9)]


def test_local_ollama_port_is_refused_by_default():
    _swallowing_connect(("127.0.0.1", 11434))


@pytest.mark.ollama
def test_ollama_marker_opens_only_the_ollama_port(network_policy):
    assert network_policy.allow_ollama is True and not network_policy.extra_hosts and network_policy.strict is False


@pytest.mark.external_network
def test_external_network_marker_without_hosts_is_an_error():
    pass


@pytest.mark.external_network("api.example.com")
def test_external_network_marker_opens_exactly_the_listed_hosts(network_policy):
    assert network_policy.extra_hosts == frozenset({"api.example.com"}) and network_policy.allow_ollama is False


@pytest.mark.integration
def test_integration_marker_grants_nothing(network_policy):
    assert network_policy.allow_ollama is False and not network_policy.extra_hosts
    assert "GROQ_API_KEY" not in os.environ


def test_ordinary_test_does_not_see_the_exported_key():
    assert "GROQ_API_KEY" not in os.environ


@pytest.mark.live_provider
def test_live_provider_test_sees_the_real_key():
    assert os.environ["GROQ_API_KEY"] == "fake-exported-key"
'''

# tests that must end in an ERROR/FAILED report (teardown failure or usage error) in the nested run
EXPECTED_TO_FAIL = {
    "test_swallowed_external_attempt_fails_at_teardown",
    "test_swallowed_dns_lookup_fails_at_teardown",
    "test_strict_mode_refuses_even_loopback",
    "test_local_ollama_port_is_refused_by_default",
    "test_external_network_marker_without_hosts_is_an_error",
}


@pytest.fixture(scope="module")
def nested_report(tmp_path_factory):
    work = tmp_path_factory.mktemp("nested_isolation")
    shutil.copy(TESTS_DIR / "conftest.py", work / "conftest.py")
    shutil.copy(TESTS_DIR / "network_guard.py", work / "network_guard.py")
    (work / "test_inner.py").write_text(INNER, encoding="utf-8")
    (work / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    integration\n    live_provider\n    ollama\n    external_network\n"
        "    network_block_expected\n    asyncio\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONUTF8": "1",
        "GROQ_API_KEY": "fake-exported-key",
    }
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-rA", "test_inner.py"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    outcomes: dict[str, set[str]] = {}
    for line in result.stdout.splitlines():
        match = re.match(r"^(PASSED|FAILED|ERROR) test_inner\.py::(\w+)", line)
        if match:
            outcomes.setdefault(match.group(2), set()).add(match.group(1))
    return outcomes, result.stdout


def test_forbidden_attempts_fail_the_test_even_when_the_code_swallows_the_error(nested_report):
    outcomes, output = nested_report
    for name in EXPECTED_TO_FAIL:
        assert outcomes.get(name, set()) & {"ERROR", "FAILED"}, f"{name} should have failed:\n{output}"


def test_allowed_and_explicitly_opted_out_tests_pass_cleanly(nested_report):
    outcomes, output = nested_report
    clean = {
        "test_swallowed_external_attempt_is_waived_when_expected",
        "test_loopback_server_started_by_the_test_is_allowed",
        "test_strict_mode_records_the_loopback_attempt",
        "test_ollama_marker_opens_only_the_ollama_port",
        "test_external_network_marker_opens_exactly_the_listed_hosts",
        "test_integration_marker_grants_nothing",
        "test_ordinary_test_does_not_see_the_exported_key",
        "test_live_provider_test_sees_the_real_key",
    }
    for name in clean:
        assert outcomes.get(name) == {"PASSED"}, f"{name}: {outcomes.get(name)}\n{output}"


def test_key_isolation_is_proven_with_a_key_that_was_really_exported(nested_report):
    """Non-vacuous: the nested run exports a key; ordinary tests must not see it, live_provider tests must."""
    outcomes, _ = nested_report
    assert outcomes["test_ordinary_test_does_not_see_the_exported_key"] == {"PASSED"}
    assert outcomes["test_live_provider_test_sees_the_real_key"] == {"PASSED"}
    assert outcomes["test_integration_marker_grants_nothing"] == {"PASSED"}


def test_child_processes_started_by_the_suite_inherit_the_network_guard():
    """The server of the aether_server fixture and uvicorn subprocesses are separate processes: the in-process guard cannot
    see them, so tests/child_guard/sitecustomize.py installs the same guard there (refused before any packet is sent)."""
    import socket

    code = (
        "import socket, sys\n"
        "if socket.socket.connect.__name__ != 'guarded_connect':\n"
        "    print('GUARD-NOT-INSTALLED')  # never open a connection from an unguarded child\n"
        "    sys.exit(0)\n"
        "def attempt(addr):\n"
        "    try:\n"
        "        socket.create_connection(addr, timeout=2).close()\n"
        "        return 'connected'\n"
        "    except Exception as exc:\n"
        "        return type(exc).__name__\n"
        "print(attempt(('127.0.0.1', 11434)), attempt(('93.184.216.34', 443)), attempt(('127.0.0.1', int(sys.argv[1]))))\n"
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        result = subprocess.run(
            [sys.executable, "-c", code, str(listener.getsockname()[1])],
            capture_output=True,
            text=True,
            timeout=60,
            env=os.environ.copy(),
        )
    finally:
        listener.close()
    assert result.returncode == 0, result.stderr
    assert "GUARD-NOT-INSTALLED" not in result.stdout, "the child did not load tests/child_guard/sitecustomize.py"
    ollama, external, own_loopback = result.stdout.split()
    assert ollama == "UnexpectedNetworkConnection" and external == "UnexpectedNetworkConnection"
    assert own_loopback == "connected", "loopback servers started by the tests must stay reachable"
