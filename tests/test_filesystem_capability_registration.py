from pathlib import Path
import pytest
from aether.intelligence.architect import build_heuristic_workforce
from aether.team.team import Team
from aether.team.config import TeamConfig, AgentConfig, Relationship
from aether.core.security import PathSandbox
from aether.coordination.events import EventEmitter, EventType
from aether.tools.base import ToolExecutionContext


def test_autoarchitect_coordinators_have_filesystem_capabilities():
    """All AutoArchitect coordinator blueprints must provide filesystem capabilities."""
    market_wf = build_heuristic_workforce("Analisi competitor e prezzi di mercato")
    lead = next(a for a in market_wf.agents if a.name == "Intelligence Lead")
    assert "filesystem_tools" in lead.skills

    tech_wf = build_heuristic_workforce("Sviluppo software e test automatici python")
    tech_lead = next(a for a in tech_wf.agents if a.name == "Tech Lead")
    assert any(s in tech_lead.skills for s in ("filesystem", "filesystem_tools"))

    finance_wf = build_heuristic_workforce("Analisi bilancio e report kpi finanziari")
    finance_lead = next(a for a in finance_wf.agents if a.name == "Finance Director")
    assert any(s in finance_lead.skills for s in ("filesystem", "filesystem_tools"))

    generic_wf = build_heuristic_workforce("Organizzazione eventi aziendali e logistica")
    squad_lead = next(a for a in generic_wf.agents if a.name == "Squad Lead")
    assert any(s in squad_lead.skills for s in ("filesystem", "filesystem_tools"))


def test_team_assembly_registers_filesystem_tools_selectively(tmp_path: Path):
    """Verify filesystem tools are registered for agents with filesystem skills, but not restricted specialists."""
    sandbox = PathSandbox(tmp_path / "files")
    emitter = EventEmitter()

    team_cfg = TeamConfig(
        name="TestSquad",
        agents=[
            AgentConfig(
                name="Coordinator",
                role="Manager",
                skills=["web_search", "filesystem_tools"],
                relationships=[Relationship(type="delegates_to", target="Specialist")],
            ),
            AgentConfig(
                name="Specialist",
                role="Pure Web Researcher",
                skills=["web_search"],
            ),
            AgentConfig(
                name="Writer",
                role="Report Writer",
                skills=["filesystem_tools"],
            ),
        ],
    )

    team = Team(team_cfg, sandbox=sandbox, emitter=emitter)

    coord = team._agents["Coordinator"]
    specialist = team._agents["Specialist"]
    writer = team._agents["Writer"]

    # Coordinator should have filesystem tools
    coord_tool_names = [t.name for t in coord.tool_registry.list_tools()]
    assert "write_file" in coord_tool_names
    assert "read_file" in coord_tool_names
    assert "list_directory" in coord_tool_names
    assert "patch_file" in coord_tool_names
    assert "delete_file" in coord_tool_names
    assert "write_file" in coord.tools

    # Pure web specialist should NOT have filesystem tools
    specialist_tool_names = [t.name for t in specialist.tool_registry.list_tools()]
    assert "write_file" not in specialist_tool_names
    assert "read_file" not in specialist_tool_names

    # Writer should have filesystem tools
    writer_tool_names = [t.name for t in writer.tool_registry.list_tools()]
    assert "write_file" in writer_tool_names

    # Coordinator's delegation tool for Specialist should reflect Specialist's tools
    spec_tool = coord.tool_registry.get("Specialist")
    assert spec_tool is not None
    assert "Tools: [search_web]" in spec_tool.description


def test_write_file_execution_creates_file_and_emits_event(tmp_path: Path):
    """Executing write_file inside sandbox creates file, records artifact and emits FILE_CREATED event."""
    sandbox = PathSandbox(tmp_path / "files")
    emitter = EventEmitter()

    emitted_events = []
    emitter.on(EventType.FILE_CREATED, lambda e: emitted_events.append(e))

    team_cfg = TeamConfig(
        name="TestSquad",
        agents=[
            AgentConfig(
                name="Intelligence Lead",
                role="Squad Coordinator",
                skills=["web_search", "search_knowledge", "filesystem_tools"],
            ),
        ],
    )

    team = Team(team_cfg, sandbox=sandbox, emitter=emitter)
    lead = team._agents["Intelligence Lead"]

    write_tool = lead.tool_registry.get("write_file")
    assert write_tool is not None

    artifacts = []
    context = ToolExecutionContext(
        task_id="task_123",
        agent_name="Intelligence Lead",
        artifacts=artifacts,
    )

    content = "* Exterior detailing\n* Interior deep cleaning\n* Ceramic coating\n"
    result = write_tool.execute({"path": "carshine-test.md", "content": content}, context=context)

    assert "Successfully created file 'carshine-test.md'" in result

    # Check file exists on disk inside sandbox
    target_file = tmp_path / "files" / "carshine-test.md"
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == content

    # Check event emitted
    assert len(emitted_events) == 1
    evt = emitted_events[0]
    assert evt.event_type == EventType.FILE_CREATED
    assert evt.agent_name == "Intelligence Lead"
    assert evt.metadata["path"] == "carshine-test.md"
    assert evt.metadata["action"] == "created"

    # Check artifact metadata recorded
    assert len(artifacts) == 1
    assert artifacts[0]["path"] == "carshine-test.md"
    assert artifacts[0]["action"] == "created"
