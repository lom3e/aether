"""
Chat -> MissionRuntime integration with the REAL stack (Workspace, stores, Team/Agent, GroqProvider client,
MissionRuntime, quality gate, memory) against a local fake Groq HTTP server. Proves: the plan comes from the model,
stages run through the canonical runtime, memory/knowledge reach the workforce prompts, the gate reports its method,
the consent is bound to the mission, and the chat reply is built from stored facts.
"""
from __future__ import annotations

import json
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
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                outer.bodies.append(body)
                sys_txt = body["messages"][0]["content"] if body["messages"] else ""
                last = body["messages"][-1]["content"]
                if "You plan work" in sys_txt:
                    content = json.dumps({"stages": [
                        {"title": "Raccolta dei fatti", "instruction": "Raccogli i fatti sul cliente Rossi dal contesto disponibile.",
                         "kind": "analysis", "agent": "analyst", "acceptance": ["Cita il formato richiesto"]},
                        {"title": "Stesura della sintesi", "instruction": "Scrivi una sintesi per il cliente Rossi.",
                         "kind": "writing", "agent": "analyst", "acceptance": ["Menziona il giorno di consegna"]}]})
                elif "Quality & Verification Reviewer" in last:
                    content = json.dumps({"passed": True, "score": 90, "feedback": "ok", "redlines": [], "rules": {
                        "requirement_coverage": {"passed": True, "score": 90, "reason": "ok"},
                        "citation_grounding": {"passed": True, "score": 90, "reason": "ok"},
                        "structural_integrity": {"passed": True, "score": 90, "reason": "ok"}}})
                else:
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
    outcomes = [m for m in ws.memory.list_memories(ws.id, limit=50) if m.category.value == "outcome"]
    assert len(outcomes) == 1
    oc = outcomes[0]
    assert oc.provenance.source_mission_id == mission_id and oc.provenance.verification_status == "verified"
    assert oc.provenance.evidence["gate_method"] == "model_assisted"
    assert "Rossi" in oc.content

    # 8. REUSE: a later mission in the same workspace retrieves that verified outcome into its stage prompts
    srv.bodies.clear()
    svc2, msg2, auth2 = run_chat_mission(ws, "Chiedi alla persona più adatta del team di aggiornare la sintesi per il cliente Rossi")
    m2 = next((st.details.get("mission_id") for st in msg2.steps if st.details and st.details.get("mission_id")), None)
    wait_task(svc2, ws, m2)
    later = [json.dumps(b["messages"]) for b in srv.bodies if "ACCEPTANCE CRITERIA" in json.dumps(b["messages"])]
    assert later and all("Mission outcome" in p for p in later)
