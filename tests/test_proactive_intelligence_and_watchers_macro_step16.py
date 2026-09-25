import json
import pytest
from pathlib import Path
from fastapi import Request

from aether.proactive.models import (
    Watcher,
    WatcherType,
    WatcherStatus,
    ProactiveSuggestion,
    SuggestionCategory,
    SuggestionPriority,
    SuggestionStatus,
    WatcherEvent,
)
from aether.proactive.store import ProactiveStore
from aether.proactive.engine import ProactiveIntelligenceEngine
from aether.workspace.workspace import Workspace
from aether.personal.service import PersonalAgentService
from aether.personal.models import IntentTier
from aether.content.models import Campaign, PlatformType, RepurposedVariant, ContentStatus
from aether.client.models import ClientProfile
from aether.benchmarking.models import EvolutionProposal
from aether.server.routes import (
    CreateWatcherPayload,
    list_proactive_suggestions_route,
    generate_proactive_suggestions_route,
    accept_proactive_suggestion_route,
    dismiss_proactive_suggestion_route,
    list_ambient_watchers_route,
    create_ambient_watcher_route,
    check_ambient_watcher_route,
    check_all_ambient_watchers_route,
    delete_ambient_watcher_route,
)


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "test_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)


def test_proactive_models():
    """Verify data model serialization and defaults for watchers and suggestions."""
    watcher = Watcher(
        name="Docs Watcher",
        description="Monitor architecture updates",
        watcher_type=WatcherType.FILE_CHANGE,
        target="docs/arch.md",
        action_id="knowledge.search",
        auto_trigger=True,
    )
    d = watcher.to_dict()
    assert d["watcher_type"] == "file_change"
    assert d["status"] == "active"
    assert d["auto_trigger"] is True

    restored = Watcher.from_dict(d)
    assert restored.name == "Docs Watcher"
    assert restored.watcher_type == WatcherType.FILE_CHANGE

    sug = ProactiveSuggestion(
        category=SuggestionCategory.AUTOMATION_DISCOVERY,
        title="Weekly Automation",
        description="Schedule weekly sync",
        proposed_action_id="content.repurpose",
        priority=SuggestionPriority.HIGH,
    )
    sug_dict = sug.to_dict()
    assert sug_dict["category"] == "automation_discovery"
    assert sug_dict["priority"] == "high"
    assert sug_dict["status"] == "pending"

    restored_sug = ProactiveSuggestion.from_dict(sug_dict)
    assert restored_sug.title == "Weekly Automation"


def test_proactive_store(tmp_path: Path):
    """Verify SQLite persistence for Watchers, Suggestions, and Events."""
    db_path = tmp_path / "proactive_test.db"
    store = ProactiveStore(db_path)

    # 1. Watchers
    w = Watcher(name="Config Monitor", target="config.yaml", watcher_type=WatcherType.FILE_CHANGE)
    store.save_watcher(w)

    fetched = store.get_watcher(w.id)
    assert fetched is not None
    assert fetched.name == "Config Monitor"

    all_w = store.list_watchers()
    assert len(all_w) == 1

    updated_w = store.update_watcher_status(w.id, WatcherStatus.PAUSED)
    assert updated_w.status == WatcherStatus.PAUSED

    # 2. Suggestions
    sug = ProactiveSuggestion(
        title="Index Docs",
        category=SuggestionCategory.KNOWLEDGE_INGESTION,
        proposed_action_id="knowledge.search",
    )
    store.save_suggestion(sug)

    sug_list = store.list_suggestions(status=SuggestionStatus.PENDING.value)
    assert len(sug_list) == 1

    accepted = store.update_suggestion_status(sug.id, SuggestionStatus.ACCEPTED)
    assert accepted.status == SuggestionStatus.ACCEPTED
    assert accepted.resolved_at is not None

    # 3. Events
    evt = WatcherEvent(watcher_id=w.id, event_type="trigger", details={"delta": "hash_diff"})
    store.save_event(evt)
    events = store.list_events(watcher_id=w.id)
    assert len(events) == 1
    assert events[0].event_type == "trigger"

    # Delete watcher
    assert store.delete_watcher(w.id) is True
    assert store.get_watcher(w.id) is None


def test_proactive_engine_workspace_pattern_scan(temp_workspace: Workspace):
    """Verify proactive intelligence engine detecting workspace opportunities."""
    engine = temp_workspace.proactive_engine

    # Seed workspace with content campaigns and variants
    camp = temp_workspace.content.create_campaign(Campaign(name="Q3 Growth Campaign"))
    var = RepurposedVariant(
        item_id=camp.id,
        platform=PlatformType.LINKEDIN,
        title="Post 1",
        body="Content",
        status=ContentStatus.PUBLISHED,
    )
    temp_workspace.content.save_variant(var)
    temp_workspace.content.save_variant(
        RepurposedVariant(item_id=camp.id, platform=PlatformType.TWITTER_THREAD, title="Post 2", body="Tweet")
    )

    # Seed client
    temp_workspace.client_store.create_client(ClientProfile(name="Acme Health"))

    # Seed benchmarking proposal
    temp_workspace.benchmarking_store.save_proposal(
        EvolutionProposal(
            target_agent="researcher",
            benchmark_run_id="bm-123",
            title="Add Guardrails",
            rationale="Fix errors",
        )
    )

    # Seed doc
    docs_dir = temp_workspace.root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "architecture.md").write_text("# System Architecture\nCore design details.")

    # Run opportunity scan
    suggestions = engine.scan_workspace_opportunities(temp_workspace)
    assert len(suggestions) >= 3

    categories = {s.category for s in suggestions}
    assert SuggestionCategory.CONTENT_REPURPOSING in categories
    assert SuggestionCategory.PERFORMANCE_OPTIMIZATION in categories
    assert SuggestionCategory.CLIENT_FOLLOWUP in categories


def test_ambient_watcher_file_change_evaluation(temp_workspace: Workspace):
    """Verify ambient file change watcher detects modifications and logs events."""
    engine = temp_workspace.proactive_engine
    store = temp_workspace.proactive_store

    test_file = temp_workspace.root / "monitored.txt"
    test_file.write_text("initial content")

    watcher = Watcher(
        name="Text Monitor",
        watcher_type=WatcherType.FILE_CHANGE,
        target=str(test_file),
        action_id="knowledge.search",
        auto_trigger=False,
    )
    store.save_watcher(watcher)

    # 1. First check (establishes baseline hash)
    trig1, ev1, sug1 = engine.check_watcher(watcher, workspace=temp_workspace)
    assert trig1 is False
    assert sug1 is None

    # 2. Modify target file
    test_file.write_text("updated new content modified!")

    # 3. Second check (detects hash change)
    trig2, ev2, sug2 = engine.check_watcher(watcher, workspace=temp_workspace)
    assert trig2 is True
    assert ev2.event_type == "trigger"
    assert sug2 is not None
    assert "Text Monitor" in sug2.title


def test_proactive_action_executor_handlers(temp_workspace: Workspace):
    """Verify ActionExecutor running proactive suggestions and watcher actions."""
    registry = temp_workspace.action_registry
    executor = temp_workspace.actions

    assert registry.get("proactive.list_suggestions") is not None
    assert registry.get("proactive.generate_suggestions") is not None
    assert registry.get("proactive.accept_suggestion") is not None
    assert registry.get("proactive.dismiss_suggestion") is not None
    assert registry.get("proactive.list_watchers") is not None
    assert registry.get("proactive.create_watcher") is not None
    assert registry.get("proactive.check_watchers") is not None

    # 1. Create watcher via executor
    res_w = executor.execute(
        action_id="proactive.create_watcher",
        workspace_id=temp_workspace.id,
        input_data={
            "name": "Audit Watcher",
            "watcher_type": "file_change",
            "target": str(temp_workspace.root / "test.json"),
            "action_id": "knowledge.search",
        },
        auto_approve=True,
    )
    assert res_w.status.value == "success"
    watcher_id = res_w.output_data["watcher"]["id"]

    # 2. List watchers
    res_list_w = executor.execute(
        action_id="proactive.list_watchers",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert res_list_w.status.value == "success"
    assert len(res_list_w.output_data["watchers"]) >= 1

    # 3. Check watchers
    res_check = executor.execute(
        action_id="proactive.check_watchers",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert res_check.status.value == "success"
    assert "results" in res_check.output_data

    # 4. Generate suggestions
    res_gen = executor.execute(
        action_id="proactive.generate_suggestions",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert res_gen.status.value == "success"

    # Seed suggestion to test accept/dismiss
    sug = temp_workspace.proactive_store.save_suggestion(
        ProactiveSuggestion(
            title="Test Action Suggestion",
            proposed_action_id="proactive.list_watchers",
            proposed_action_args={},
        )
    )

    # 5. Accept suggestion
    res_acc = executor.execute(
        action_id="proactive.accept_suggestion",
        workspace_id=temp_workspace.id,
        input_data={"suggestion_id": sug.id},
        auto_approve=True,
    )
    assert res_acc.status.value == "success"
    assert res_acc.output_data["suggestion"]["status"] == "applied"


def test_personal_agent_proactive_intents(temp_workspace: Workspace):
    """Verify natural language classification for proactive and watcher intents."""
    service = PersonalAgentService(
        store=temp_workspace.personal_store,
        action_executor=temp_workspace.actions,
        activity_service=temp_workspace.activity,
    )

    # 1. List suggestions
    i1 = service.classify_intent("Mostra i suggerimenti proattivi e cosa mi consigli")
    assert i1.action_id == "proactive.list_suggestions"
    assert i1.tier == IntentTier.ANSWER

    # 2. Scan opportunities
    i2 = service.classify_intent("Scansiona il workspace per nuove opportunita e ottimizzazioni")
    assert i2.action_id == "proactive.generate_suggestions"
    assert i2.tier == IntentTier.DO

    # 3. Accept suggestion
    i3 = service.classify_intent("Accetta suggerimento sug-999")
    assert i3.action_id == "proactive.accept_suggestion"
    assert i3.tier == IntentTier.ACT
    assert i3.action_args.get("suggestion_id") == "sug-999"

    # 4. List watchers
    i4 = service.classify_intent("Quali watcher sono attivi e mostra elenco watcher")
    assert i4.action_id == "proactive.list_watchers"
    assert i4.tier == IntentTier.ANSWER

    # 5. Create watcher
    i5 = service.classify_intent("Crea watcher per monitorare il file docs/readme.md")
    assert i5.action_id == "proactive.create_watcher"
    assert i5.tier == IntentTier.DO


class DummyAppState:
    def __init__(self, workspace):
        self.workspace = workspace


class DummyApp:
    def __init__(self, workspace):
        self.state = DummyAppState(workspace)


@pytest.mark.asyncio
async def test_fastapi_proactive_routes(temp_workspace: Workspace):
    """Verify all proactive intelligence and ambient watcher FastAPI route handlers."""
    app = DummyApp(temp_workspace)
    req = Request(scope={"type": "http", "app": app})

    # 1. Create Watcher
    p_wat = CreateWatcherPayload(
        name="API Test Watcher",
        target="src/aether",
        watcher_type="directory_watch",
        action_id="knowledge.search",
        auto_trigger=False,
    )
    res_wat = await create_ambient_watcher_route(req, p_wat)
    assert res_wat["name"] == "API Test Watcher"
    wat_id = res_wat["id"]

    # 2. List Watchers
    watchers = await list_ambient_watchers_route(req)
    assert len(watchers) >= 1

    # 3. Check Single Watcher
    check_single = await check_ambient_watcher_route(req, wat_id)
    assert "triggered" in check_single

    # 4. Check All Watchers
    check_all = await check_all_ambient_watchers_route(req)
    assert len(check_all["results"]) >= 1

    # 5. Generate Suggestions
    res_gen = await generate_proactive_suggestions_route(req)
    assert "suggestions" in res_gen

    # Seed suggestion
    sug = temp_workspace.proactive_store.save_suggestion(
        ProactiveSuggestion(
            title="FastAPI Suggestion",
            proposed_action_id="proactive.list_watchers",
        )
    )

    # 6. List Suggestions
    suggestions = await list_proactive_suggestions_route(req)
    assert len(suggestions) >= 1

    # 7. Accept Suggestion
    res_acc = await accept_proactive_suggestion_route(req, sug.id)
    assert res_acc["suggestion"]["status"] == "applied"

    # Seed another suggestion to dismiss
    sug2 = temp_workspace.proactive_store.save_suggestion(
        ProactiveSuggestion(title="To Dismiss")
    )
    # 8. Dismiss Suggestion
    res_dis = await dismiss_proactive_suggestion_route(req, sug2.id)
    assert res_dis["status"] == "dismissed"

    # 9. Delete Watcher
    res_del = await delete_ambient_watcher_route(req, wat_id)
    assert res_del["deleted"] is True
