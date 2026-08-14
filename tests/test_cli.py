"""Tests for the Aether CLI (new team-oriented interface)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cli(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "aether.cli.main"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd or os.getcwd(),
    )


def run_cli_with_env(*args, cwd=None, env=None) -> subprocess.CompletedProcess:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "aether.cli.main"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd or os.getcwd(),
        env=process_env,
    )


class TestCliInit:
    def test_init_creates_project_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my_team")
            result = run_cli("init", project_path)

            assert result.returncode == 0, result.stderr
            assert os.path.exists(project_path)
            assert os.path.exists(os.path.join(project_path, "teams", "default.yaml"))
            assert os.path.exists(os.path.join(project_path, "aether.yaml"))
            assert os.path.exists(os.path.join(project_path, "README.md"))
            assert os.path.exists(os.path.join(project_path, "knowledge"))
            assert os.path.exists(os.path.join(project_path, "data"))

    def test_init_team_yaml_contains_agents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "test_project")
            result = run_cli("init", project_path)
            assert result.returncode == 0

            team_yaml = Path(project_path) / "teams" / "default.yaml"
            content = team_yaml.read_text()
            assert "agents:" in content
            assert "manager" in content
            assert "researcher" in content

    def test_init_current_dir(self):
        """aether init without a name initializes in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli("init", cwd=tmpdir)
            assert result.returncode == 0
            assert (Path(tmpdir) / "teams" / "default.yaml").exists()

    def test_init_with_ollama_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "ollama_team")
            result = run_cli("init", project_path, "--provider", "ollama")
            assert result.returncode == 0
            content = (Path(project_path) / "teams" / "default.yaml").read_text()
            assert "ollama" in content

    def test_init_nonempty_dir_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "nonempty")
            os.makedirs(project_path)
            (Path(project_path) / "existing.txt").write_text("content")

            result = run_cli("init", project_path)
            assert result.returncode == 1
            assert "not empty" in result.stderr.lower() or "not empty" in result.stdout.lower()


class TestCliKnowledge:
    def test_knowledge_add_text_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a team.yaml so the CLI can find it
            (Path(tmpdir) / "team.yaml").write_text("team:\n  name: t\nagents:\n  - name: a\n")
            (Path(tmpdir) / ".aether").mkdir()

            doc = Path(tmpdir) / "doc.txt"
            doc.write_text("This is a test document about GDPR compliance. " * 10)

            result = run_cli("knowledge", "add", str(doc), cwd=tmpdir)
            assert result.returncode == 0
            assert "chunk" in result.stdout.lower() or "indicizzat" in result.stdout

    def test_knowledge_list_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "team.yaml").write_text("team:\n  name: t\nagents:\n  - name: a\n")
            result = run_cli("knowledge", "list", cwd=tmpdir)
            assert result.returncode == 0
            assert "vuota" in result.stdout.lower() or "empty" in result.stdout.lower()

    def test_knowledge_add_then_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "team.yaml").write_text("team:\n  name: t\nagents:\n  - name: a\n")
            (Path(tmpdir) / ".aether").mkdir()

            doc = Path(tmpdir) / "report.md"
            doc.write_text("# Report\n\nGDPR compliance details here. " * 5)

            run_cli("knowledge", "add", str(doc), cwd=tmpdir)
            result = run_cli("knowledge", "list", cwd=tmpdir)
            assert result.returncode == 0
            assert "report.md" in result.stdout

    def test_knowledge_clear(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "team.yaml").write_text("team:\n  name: t\nagents:\n  - name: a\n")
            (Path(tmpdir) / ".aether").mkdir()

            doc = Path(tmpdir) / "doc.txt"
            doc.write_text("Content about compliance " * 5)
            run_cli("knowledge", "add", str(doc), cwd=tmpdir)

            result = run_cli("knowledge", "clear", cwd=tmpdir)
            assert result.returncode == 0
            assert "svuotata" in result.stdout or "rimossi" in result.stdout

    def test_knowledge_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "team.yaml").write_text("team:\n  name: t\nagents:\n  - name: a\n")
            (Path(tmpdir) / ".aether").mkdir()

            doc = Path(tmpdir) / "gdpr.txt"
            doc.write_text("GDPR regulation requires data protection measures. " * 5)
            run_cli("knowledge", "add", str(doc), cwd=tmpdir)

            result = run_cli("knowledge", "search", "GDPR", cwd=tmpdir)
            assert result.returncode == 0
            assert "gdpr.txt" in result.stdout

    def test_knowledge_add_path_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "team.yaml").write_text("team:\n  name: t\nagents:\n  - name: a\n")
            result = run_cli("knowledge", "add", "/nonexistent/path.txt", cwd=tmpdir)
            assert result.returncode == 1
            assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()


class TestCliTeam:
    def test_team_status_with_valid_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            team_yaml = Path(tmpdir) / "team.yaml"
            team_yaml.write_text("""
team:
  name: test-team
  provider: openai

agents:
  - name: coordinator
    role: coordinator
  - name: worker
    role: worker
""")
            result = run_cli("team", "status", cwd=tmpdir)
            assert result.returncode == 0
            assert "test-team" in result.stdout
            assert "coordinator" in result.stdout
            assert "worker" in result.stdout

    def test_team_status_no_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli("team", "status", cwd=tmpdir)
            assert result.returncode == 1

    def test_team_status_uses_explicit_workspace_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "teams").mkdir()
            (root / "aether.yaml").write_text(
                "version: '1.0'\nworkspace:\n  name: selected\n  default_team: selected\n"
            )
            (root / "teams" / "selected.yaml").write_text(
                "team:\n  name: selected\n  provider: mock\nagents:\n  - name: worker\n    role: worker\n"
            )

            result = run_cli_with_env(
                "team", "status", cwd=tmpdir, env={"AETHER_WORKSPACE": tmpdir}
            )

            assert result.returncode == 0, result.stderr
            assert "Team: selected" in result.stdout
            assert "worker" in result.stdout


class TestCliRun:
    def test_run_without_team_yaml_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli("run", "Do something", cwd=tmpdir)
            assert result.returncode == 1
            assert "team configuration 'default' not found" in result.stderr.lower()

    def test_run_with_missing_api_key_fails_gracefully(self):
        """Without an API key, run should fail with a clear message, not a traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "team.yaml").write_text("""
team:
  name: t
  provider: openai
agents:
  - name: agent
    role: assistant
""")
            import os as _os
            env = {k: v for k, v in _os.environ.items() if k != "OPENAI_API_KEY"}
            result = subprocess.run(
                [sys.executable, "-m", "aether.cli.main", "run", "test task"],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                env=env,
            )
            assert result.returncode == 1
            assert "OPENAI_API_KEY" in result.stderr or "OPENAI_API_KEY" in result.stdout
            assert "Traceback" not in result.stderr
