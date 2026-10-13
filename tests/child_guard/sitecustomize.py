"""
Test-only ``sitecustomize``: extends the network guard to Python child processes started by the test-suite (the server of
the ``aether_server`` fixture, uvicorn subprocesses of the browser tests...). It is inert unless the suite explicitly sets
``AETHER_TEST_CHILD_NETWORK_GUARD=1`` (done in tests/conftest.py *after* the pytest process started, so pytest itself is
not affected) and it only loads when this directory is on ``PYTHONPATH``.

Children may talk to loopback servers but not to the local Ollama port nor to any external host. Frozen executables ignore
PYTHONPATH and are not covered.
"""
import os
import sys

if os.environ.get("AETHER_TEST_CHILD_NETWORK_GUARD") == "1":
    try:
        import importlib.util

        _spec = importlib.util.spec_from_file_location("aether_child_network_guard", os.environ["AETHER_TEST_GUARD_FILE"])
        _guard = importlib.util.module_from_spec(_spec)
        sys.modules[_spec.name] = _guard  # dataclasses look the defining module up in sys.modules
        _spec.loader.exec_module(_guard)

        class _Permanent:  # monkeypatch-like object whose changes are never undone: the guard lives as long as the process
            def setattr(self, target, name, value):
                setattr(target, name, value)

        _guard.install_network_guard(_Permanent())
    except Exception:  # never prevent a child from starting because of the guard itself
        pass
