"""
Chat -> MissionRuntime integration with the REAL stack (Workspace, stores, Team/Agent, GroqProvider client,
MissionRuntime, quality gate, memory) against a local fake Groq HTTP server. Proves: the plan comes from the model,
stages run through the canonical runtime, memory/knowledge reach the workforce prompts, the gate reports its method,
the consent is bound to the mission, and the chat reply is built from stored facts.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import yaml

from aether.knowledge.chunk import KnowledgeChunk
from aether.memory.models import MemoryProvenance, WorkforceMemory
from aether.providers.groq_provider import GroqProvider
from aether.workspace.workspace import Workspace
from conftest import make_test_accepted_authority

KEY = "gsk_FAKEKEY_for_local_server_0123456789"


class FakeGroq:
    def __init__(self):
        self.bodies: list[dict] = []
        # Simulated provider rate limit: while ``fail_remaining`` > 0, a request whose last message contains
        # ``fail_when`` is answered with HTTP 429 and a Retry-After far above the provider's bounded wait.
        self.fail_when: str | None = None
        self.fail_remaining = 0
        # Simulated slow model: a request containing ``delay_when`` is answered after ``delay`` seconds.
        self.delay_when: str | None = None
        self.delay = 0.0
        # Simulated tool use: for a request containing ``tool_when`` the model first asks to write a file, then answers.
        self.tool_when: str | None = None
        self.tool_args: dict = {}
        self.tool_results: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                outer.bodies.append(body)
                sys_txt = body["messages"][0]["content"] if body["messages"] else ""
                last = body["messages"][-1]["content"]
                if outer.delay_when and outer.delay_when in json.dumps(body["messages"]):
                    import time as _t
                    _t.sleep(outer.delay)
                if outer.fail_when and outer.fail_remaining > 0 and outer.fail_when in json.dumps(body["messages"]):
                    outer.fail_remaining -= 1
                    raw = json.dumps({"error": {"message": "Rate limit reached for model"}}).encode()
                    self.send_response(429); self.send_header("Retry-After", "120")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                    return
                if "You plan work" in sys_txt:
                    content = json.dumps({"stages": [
                        {"title": "Raccolta dei fatti", "instruction": "Raccogli i fatti sul cliente Rossi dal contesto disponibile.",
                         "kind": "analysis", "agent": "analyst", "acceptance": ["Cita il formato richiesto"]},
                        {"title": "Stesura della sintesi", "instruction": "Scrivi una sintesi per il cliente Rossi.",
                         "kind": "writing", "agent": "analyst", "acceptance": ["Menziona il giorno di consegna"]}]})
                elif outer.tool_when and outer.tool_when in json.dumps(body["messages"]) and not any(
                        m.get("role") == "tool" for m in body["messages"]):
                    raw = json.dumps({"model": body["model"], "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": "write_file", "arguments": json.dumps(outer.tool_args)}}]},
                        "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                    return
                elif "Quality & Verification Reviewer" in last:
                    content = json.dumps({"passed": True, "score": 90, "feedback": "ok", "redlines": [], "rules": {
                        "requirement_coverage": {"passed": True, "score": 90, "reason": "ok"},
                        "citation_grounding": {"passed": True, "score": 90, "reason": "ok"},
                        "structural_integrity": {"passed": True, "score": 90, "reason": "ok"}}})
                else:
                    for m in body["messages"]:
                        if m.get("role") == "tool":
                            outer.tool_results.append(str(m.get("content")))
                    content = "Rossi vuole il report in PDF ogni lunedì entro le 9."
                raw = json.dumps({"model": body["model"], "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                                  "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/openai/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


@pytest.fixture
def stack(tmp_path, monkeypatch):
    srv = FakeGroq()
    monkeypatch.setattr(GroqProvider, "DEFAULT_BASE_URL", srv.url)
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    ws = Workspace.init(tmp_path / "ws", "Chat Mission WS")
    (ws.teams_dir / "default.yaml").write_text(yaml.safe_dump({
        "team": {"name": "default", "provider": "groq", "model": "qwen/test-model"},
        "agents": [{"name": "analyst", "role": "Research Analyst", "instructions": "Sei un analista.", "provider": "groq", "model": "qwen/test-model"}],
    }), encoding="utf-8")
    ws.memory.create_memory(WorkforceMemory.create(
        workspace_id=ws.id, category="preference", summary="Rossi report", content="Il cliente Rossi vuole il report settimanale ogni lunedì in formato PDF.",
        provenance=MemoryProvenance(source_entity="user_instruction", verification_status="user_stated")))
    ws.knowledge.add(KnowledgeChunk(content="Procedura clienti: il report del cliente Rossi va inviato il lunedì mattina.", source="procedure.md", chunk_index=1))
    yield ws, srv
    try:
        ws.personal.shutdown()
    except Exception:
        pass
    ws.close(); srv.close()


def run_chat_mission(ws, prompt):
    from aether.personal.models import IntentTier
    svc = ws.personal
    intent = svc.classify_intent(prompt)
    assert intent.tier == IntentTier.DELEGATE, intent
    _, authority = make_test_accepted_authority(ws, constraints=[f"allow:workforce.delegate,workforce.delegate:{ws.id}"], title="Rossi")
    msg = svc.process_prompt(prompt=prompt, workspace_id=ws.id, session_id="s-1", authority=authority)
    return svc, msg, authority


def wait_task(svc, ws, mission_id, timeout=60):
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = ws.missions.get_mission(mission_id)
        if m and m.status.value in ("completed", "failed", "cancelled", "interrupted"):
            time.sleep(0.5)
            return m
        time.sleep(0.3)
    raise AssertionError("mission did not finish")


def test_chat_delegation_runs_on_mission_runtime_with_context_and_honest_outcome(stack):
    ws, srv = stack
    prompt = "Chiedi alla persona più adatta del team di preparare una sintesi per il cliente Rossi"
    svc, msg, auth = run_chat_mission(ws, prompt)
    mission_id = msg.mission_id or msg.metadata.get("mission_id") or next(
        (st.details.get("mission_id") for st in msg.steps if st.details and st.details.get("mission_id")), None)
    assert mission_id, msg.to_dict()
    mission = wait_task(svc, ws, mission_id)

    # 1. the plan came from the model, with real stages and acceptance criteria, stored as a real mission
    assert mission.metadata["plan_source"] == "llm" and mission.metadata["plan_model"] == "qwen/test-model"
    assert [m.title for m in mission.milestones] == ["Raccolta dei fatti", "Stesura della sintesi"]
    # 2. stages really ran on MissionRuntime, truthfully
    assert mission.status.value == "completed", mission.error
    execs = [ws.missions.get_execution(e) for e in mission.execution_ids]
    stage_states = [em.status.value for em in ws.missions.get_execution_milestones(execs[0].id)]
    assert stage_states == ["completed", "completed"]
    # 3. memory + knowledge actually reached the workforce prompts (what the model SAW)
    stage_prompts = [json.dumps(b["messages"]) for b in srv.bodies if "ACCEPTANCE CRITERIA" in json.dumps(b["messages"])]
    assert stage_prompts, "no stage prompt captured"
    assert all("formato PDF" in p and "procedure.md" in p for p in stage_prompts)
    # 4. the acceptance criteria were handed to the agent
    assert any("Cita il formato richiesto" in p for p in stage_prompts)
    # 5. consent is bound to the mission it authorised
    consent = ws.personal_store.get_consent(auth.proposal_id, auth.proposal_version)
    assert consent.mission_id == mission_id
    # 6. the key never travelled in a URL and the provider is the configured one
    assert all(b["model"] == "qwen/test-model" for b in srv.bodies)


    # 7. the gate says HOW it verified, and only a verified outcome is written to memory
    all_outcomes = [m for m in ws.memory.list_memories(ws.id, limit=50) if m.category.value == "outcome"]
    # The stages only produced text, so the runtime saved it as a real deliverable: that verified deliverable has its
    # own outcome memory next to the mission outcome. Both exist only because the gate passed.
    assert all(m.provenance.verification_status == "verified" for m in all_outcomes)
    assert [m.summary for m in all_outcomes if m.summary.startswith("Verified Deliverable")], "deliverable outcome missing"
    outcomes = [m for m in all_outcomes if not m.summary.startswith("Verified Deliverable")]
    assert len(outcomes) == 1
    oc = outcomes[0]
    assert oc.provenance.source_mission_id == mission_id and oc.provenance.verification_status == "verified"
    assert oc.provenance.evidence["gate_method"] == "model_assisted"
    assert "Rossi" in oc.content

    # 7b. The stages only wrote text: that text must still be a real, openable, verified deliverable (not a log line)
    delivs = ws.missions.list_deliverables(mission_id)
    assert len(delivs) == 1 and delivs[0].status == "verified", [(d.name, d.status) for d in delivs]
    saved = Path(delivs[0].path)
    assert saved.is_file() and saved.parent.name == "deliverables" and saved.suffix == ".md"
    assert saved.read_text(encoding="utf-8").startswith("# ")
    assert delivs[0].metadata.get("synthesized_from_stage_output") is True

    # 7c. The task summary the user is notified with carries the result itself, not only a count
    summaries = [t.result_summary or "" for t in svc.task_manager.list_tasks(workspace_id=ws.id)]
    assert any("Missione completata" in x and "Risultato" in x and "`" in x for x in summaries), summaries

    # 8. REUSE: a later mission in the same workspace retrieves that verified outcome into its stage prompts
    srv.bodies.clear()
    svc2, msg2, auth2 = run_chat_mission(ws, "Chiedi alla persona più adatta del team di aggiornare la sintesi per il cliente Rossi")
    m2 = next((st.details.get("mission_id") for st in msg2.steps if st.details and st.details.get("mission_id")), None)
    wait_task(svc2, ws, m2)
    later = [json.dumps(b["messages"]) for b in srv.bodies if "ACCEPTANCE CRITERIA" in json.dumps(b["messages"])]
    assert later and all("Mission outcome" in p for p in later)


def test_rate_limited_stage_fails_honestly_and_retry_resumes_without_redoing_finished_work(stack):
    """A provider 429 on stage 2 must not lose stage 1: the mission fails truthfully, the retry runs ONLY stage 2."""
    import asyncio
    from aether.missions.runtime import MissionRuntime

    ws, srv = stack
    srv.fail_when, srv.fail_remaining = "Scrivi una sintesi", 10_000
    prompt = "Chiedi alla persona più adatta del team di preparare una sintesi per il cliente Rossi"
    svc, msg, auth = run_chat_mission(ws, prompt)
    mission_id = next(st.details.get("mission_id") for st in msg.steps if st.details and st.details.get("mission_id"))
    mission = wait_task(svc, ws, mission_id)

    assert mission.status.value == "failed"
    failed_tasks = [x for x in svc.task_manager.list_tasks(workspace_id=ws.id) if x.mission_id == mission_id]
    assert failed_tasks and failed_tasks[0].status.value == "failed", "a failed mission must not be shown as a completed task"
    execution = ws.missions.get_execution(mission.execution_ids[0])
    stages = {em.milestone_id: em for em in ws.missions.get_execution_milestones(execution.id)}
    states = [stages[m.id].status.value for m in mission.milestones]
    assert states == ["completed", "failed"], states
    failed = stages[mission.milestones[1].id]
    assert "rate limit" in (failed.error or "").lower() and "120" in (failed.error or "")   # says why and for how long
    assert ws.missions.list_deliverables(mission_id) == [], "nothing may be presented as a result of a failed run"
    stage1_runs = sum("CURRENT STAGE: Raccolta dei fatti" in json.dumps(b["messages"]) for b in srv.bodies)
    assert stage1_runs >= 1   # a stage may use more than one model call; what matters is that retry adds none

    # The provider recovers: retrying resumes the same execution and runs only the failed stage.
    srv.fail_remaining = 0

    async def _retry():
        runtime = MissionRuntime(ws)
        await runtime.retry_mission(mission_id)      # exactly what POST /missions/{id}/retry does: no authority passed
        handle = runtime._active_executions.get(execution.id)
        if handle is not None and handle.task is not None:
            await handle.task
        await runtime.shutdown()

    asyncio.run(_retry())
    final = ws.missions.get_mission(mission_id)
    assert final.status.value == "completed", final.error
    assert sum("CURRENT STAGE: Raccolta dei fatti" in json.dumps(b["messages"]) for b in srv.bodies) == stage1_runs, "stage 1 was redone"
    delivs = ws.missions.list_deliverables(mission_id)
    assert len(delivs) == 1 and delivs[0].status == "verified"


def test_authority_of_another_delegation_cannot_continue_this_mission(stack):
    import asyncio
    from aether.core.execution import UnauthorizedExecutionError
    from aether.missions.runtime import MissionRuntime

    ws, srv = stack
    srv.fail_when, srv.fail_remaining = "Scrivi una sintesi", 10_000
    svc, msg, auth = run_chat_mission(ws, "Chiedi alla persona più adatta del team di preparare una sintesi per il cliente Rossi")
    mission_id = next(st.details.get("mission_id") for st in msg.steps if st.details and st.details.get("mission_id"))
    wait_task(svc, ws, mission_id)
    _, foreign = make_test_accepted_authority(ws, constraints=[f"allow:workforce.delegate,workforce.delegate:{ws.id}"], title="Altro")
    assert foreign.proposal_id != auth.proposal_id

    async def _try():
        runtime = MissionRuntime(ws)
        try:
            await runtime.retry_mission(mission_id, authority=foreign)
        finally:
            await runtime.shutdown()

    with pytest.raises(UnauthorizedExecutionError):
        asyncio.run(_try())


def test_cancelling_a_chat_mission_really_stops_it(stack):
    """Cancel is what POST /missions/{id}/cancel does (another runtime than the one executing the chat mission)."""
    import asyncio
    import time
    from aether.missions.runtime import MissionRuntime

    ws, srv = stack
    srv.delay_when, srv.delay = "CURRENT STAGE: Raccolta dei fatti", 2.0
    svc, msg, auth = run_chat_mission(ws, "Chiedi alla persona più adatta del team di preparare una sintesi per il cliente Rossi")
    mission_id = next(st.details.get("mission_id") for st in msg.steps if st.details and st.details.get("mission_id"))

    deadline = time.time() + 20
    while not any("CURRENT STAGE: Raccolta dei fatti" in json.dumps(b["messages"]) for b in srv.bodies):
        assert time.time() < deadline, "the first stage never started"
        time.sleep(0.05)

    async def _cancel():
        runtime = MissionRuntime(ws)
        try:
            await runtime.cancel_mission(mission_id, reason="user pressed cancel")
        finally:
            await runtime.shutdown()

    asyncio.run(_cancel())
    time.sleep(srv.delay + 2.5)                       # the slow model answers, the mission must NOT carry on

    mission = ws.missions.get_mission(mission_id)
    execution = ws.missions.get_execution(mission.execution_ids[0])
    assert mission.status.value == "cancelled", mission.status
    assert execution.status.value == "cancelled", execution.status
    assert not any("CURRENT STAGE: Stesura della sintesi" in json.dumps(b["messages"]) for b in srv.bodies), "stage 2 ran after cancel"
    assert [d for d in ws.missions.list_deliverables(mission_id) if d.status == "verified"] == []
    # ...and the user-facing task says so instead of "Completed".
    tasks = [x for x in svc.task_manager.list_tasks(workspace_id=ws.id) if x.mission_id == mission_id]
    assert tasks and tasks[0].status.value in ("cancelled", "failed"), [x.status for x in tasks]


def test_agents_of_an_accepted_delegation_can_write_their_report_file(stack):
    """Regression: write_file used to be refused under a workforce.delegate authority, so no stage could save a file."""
    ws, srv = stack
    (ws.teams_dir / "default.yaml").write_text(yaml.safe_dump({
        "team": {"name": "default", "provider": "groq", "model": "qwen/test-model"},
        "agents": [{"name": "analyst", "role": "Research Analyst", "instructions": "Sei un analista.", "provider": "groq",
                    "model": "qwen/test-model", "tools": ["write_file", "search_knowledge"]}],
    }), encoding="utf-8")
    srv.tool_when = "CURRENT STAGE: Stesura della sintesi"
    srv.tool_args = {"path": "sintesi_rossi.md", "content": "# Sintesi Rossi\n\nRossi vuole il report in PDF ogni lunedì entro le 9.\n"}
    svc, msg, auth = run_chat_mission(ws, "Chiedi alla persona più adatta del team di preparare una sintesi per il cliente Rossi")
    mission_id = next(st.details.get("mission_id") for st in msg.steps if st.details and st.details.get("mission_id"))
    mission = wait_task(svc, ws, mission_id)

    assert srv.tool_results, "the model never received a tool result"
    assert "unauthorized" not in " ".join(srv.tool_results).lower() and "scope" not in " ".join(srv.tool_results).lower(), srv.tool_results
    assert mission.status.value == "completed", mission.error
    names = [d.name for d in ws.missions.list_deliverables(mission_id)]
    assert names == ["sintesi_rossi.md"], names
    written = next(Path(d.path) for d in ws.missions.list_deliverables(mission_id))
    assert written.is_file() and "Sintesi Rossi" in written.read_text(encoding="utf-8")

    # ...and it is visible the way the UI reads it: listed by the missions API, verified, and previewable.
    import asyncio
    from types import SimpleNamespace
    from aether.server.routes import get_deliverable_preview, list_mission_deliverables
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(workspace=ws)))
    listed = asyncio.run(list_mission_deliverables(req, mission_id))
    assert [(d["name"], d["status"]) for d in listed] == [("sintesi_rossi.md", "verified")]
    assert listed[0]["size_bytes"] > 0
    preview = asyncio.run(get_deliverable_preview(req, mission_id, listed[0]["id"]))
    assert preview["preview_available"] and "Sintesi Rossi" in preview["content"]


def test_a_resumed_mission_drops_the_stale_error_and_registers_its_file_once(stack):
    """After a 429 failure and a successful retry: no old error in the current state (kept as history), one deliverable."""
    import asyncio
    from aether.missions.runtime import MissionRuntime

    ws, srv = stack
    (ws.teams_dir / "default.yaml").write_text(yaml.safe_dump({
        "team": {"name": "default", "provider": "groq", "model": "qwen/test-model"},
        "agents": [{"name": "analyst", "role": "Research Analyst", "instructions": "Sei un analista.", "provider": "groq",
                    "model": "qwen/test-model", "tools": ["write_file"]}],
    }), encoding="utf-8")
    srv.tool_when = "CURRENT STAGE: Stesura della sintesi"
    srv.tool_args = {"path": "sintesi_rossi.md", "content": "# Sintesi Rossi\n\nRossi vuole il report in PDF ogni lunedì entro le 9.\n"}
    srv.fail_when, srv.fail_remaining = "Stesura della sintesi", 10_000        # the stage that writes the file hits the rate limit
    srv.fail_when = "Stesura della sintesi"
    svc, msg, auth = run_chat_mission(ws, "Chiedi alla persona più adatta del team di preparare una sintesi per il cliente Rossi")
    mission_id = next(st.details.get("mission_id") for st in msg.steps if st.details and st.details.get("mission_id"))
    mission = wait_task(svc, ws, mission_id)
    assert mission.status.value == "failed"
    execution = ws.missions.get_execution(mission.execution_ids[0])
    assert "rate limit" in (execution.error_message or "").lower()

    srv.fail_remaining = 0

    async def _retry():
        runtime = MissionRuntime(ws)
        await runtime.retry_mission(mission_id)
        handle = runtime._active_executions.get(execution.id)
        if handle is not None and handle.task is not None:
            await handle.task
        await runtime.shutdown()

    asyncio.run(_retry())
    final = ws.missions.get_mission(mission_id)
    assert final.status.value == "completed", final.error
    done = ws.missions.get_execution(execution.id)
    assert not done.error_message and not done.error_details, "the old 429 is still shown as the current error"
    assert any("rate limit" in h["error"].lower() for h in done.metadata["error_history"]), "the failure must stay in the audit history"
    assert all(not (em.error or "") for em in ws.missions.get_execution_milestones(execution.id))

    delivs = ws.missions.list_deliverables(mission_id)
    assert [(d.name, d.status, d.file_available) for d in delivs] == [("sintesi_rossi.md", "verified", True)], [(d.name, d.status) for d in delivs]
    assert len({d.path for d in delivs}) == 1
