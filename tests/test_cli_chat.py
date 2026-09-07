import argparse
from unittest.mock import MagicMock, patch
import pytest
from aether.cli.main import main, _cmd_chat
from aether.core.execution import ExecutionResult


def test_cli_chat_argument_parser():
    with patch("sys.argv", ["aether", "chat", "--provider", "ollama", "--model", "llama3"]):
        with patch("aether.cli.main._cmd_chat") as mock_chat:
            main()
            mock_chat.assert_called_once()
            args = mock_chat.call_args[0][0]
            assert args.command == "chat"
            assert args.provider == "ollama"
            assert args.model == "llama3"


def test_cli_chat_repl_loop_exit():
    args = argparse.Namespace(provider="ollama", model="llama3")

    mock_team = MagicMock()
    mock_team.config.name = "Test Workforce"
    mock_team.config.default_provider = "ollama"
    mock_team.config.default_model = "llama3"
    mock_team.agents.return_value = []
    mock_team.emitter = MagicMock()

    mock_ws = MagicMock()
    mock_ws.load_team.return_value = mock_team

    # Simulate user typing a task, then /quit
    user_inputs = ["Summarize roadmap", "/quit"]

    with patch("aether.cli.main._workspace_from_context", return_value=mock_ws), \
         patch("aether.cli.main._build_provider", return_value=MagicMock()), \
         patch("builtins.input", side_effect=user_inputs):

        mock_team.run.return_value = ExecutionResult(success=True, output="Summary of roadmap")
        _cmd_chat(args)

        mock_team.run.assert_called_once_with("Summarize roadmap")
