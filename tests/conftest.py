"""
Global pytest fixtures for test isolation.
Resets app state and data directory overrides between test runs.
"""
import os
import pytest
from aether.server.app import app
from aether.core.paths import set_aether_data_dir


@pytest.fixture(autouse=True)
def reset_app_state_and_paths():
    """Ensure clean runtime state before and after each test."""
    # Pre-test cleanup
    app.state.is_shutting_down = False
    app.state.session_token = None
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}
    set_aether_data_dir(None)
    os.environ.pop("AETHER_DATA_DIR", None)
    os.environ.pop("AETHER_SESSION_TOKEN", None)

    yield

    # Post-test cleanup
    app.state.is_shutting_down = False
    app.state.session_token = None
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}
    set_aether_data_dir(None)
    os.environ.pop("AETHER_DATA_DIR", None)
    os.environ.pop("AETHER_SESSION_TOKEN", None)
