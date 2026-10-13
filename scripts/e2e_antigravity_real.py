#!/usr/bin/env python
"""
Controlled REAL end-to-end: Aether -> Google Antigravity, in a throw-away workspace and a throw-away git repo.

Run it from a terminal INSIDE Antigravity (its integrated terminal), because `agentapi` authenticates to the
running language server through environment variables that only that terminal gets (ANTIGRAVITY_LS_ADDRESS and a
CSRF token). Aether never reads those from other processes.

    cd <repo>/aether
    .venv/bin/python -B scripts/e2e_antigravity_real.py [--out DIR] [--no-groq] [--timeout 600]

What it does (one Antigravity session, nothing else is touched):
  1. creates DIR/project (clean git repo with a stub `calc.add` and failing unittests) and DIR/ws (Aether workspace)
  2. chat prompt -> proposal -> accept (consent) -> dispatch -> human approval  (the real route functions)
  3. the REAL Antigravity run executes; events/run state are read from the durable run store
  4. an authorised `coding.run_tests` action is queued and approved; the mission is finalised from facts
  5. independent verification: this script runs the tests itself and inspects `git` in the project
  6. side-effect checks: ~/.aether unchanged, exactly one new Antigravity conversation, Aether source untouched
Everything is written to DIR/report.json. No secret is printed or stored. With --no-groq the planner/classifier
use no remote model (the Groq key, when used, is read in-process from the workspace vault and never shown).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import yaml

REQUIRED_ENV = "ANTIGRAVITY_LS_ADDRESS"
T0 = time.time()
REPORT: dict = {"steps": [], "checks": {}}
OUT: Path


def step(name: str, **kw) -> None:
    REPORT["steps"].append({"step": name, "t": round(time.time() - T0, 1), **kw})
    (OUT / "report.json").write_text(json.dumps(REPORT, indent=2, default=str), encoding="utf-8")
    print(f"[{round(time.time() - T0, 1):>7}s] {name}", {k: v for k, v in kw.items()}, flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    REPORT["checks"][name] = {"ok": bool(ok), "detail": detail}
    print(f"   {'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def listing(root: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in root.rglob("*") if p.is_file()} if root.exists() else {}


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-groq", action="store_true")
    ap.add_argument("--timeout", type=float, default=600.0)
    args = ap.parse_args()

    if not os.environ.get(REQUIRED_ENV):
        print(f"{REQUIRED_ENV} is not set: run this from Antigravity's integrated terminal. Nothing was started.")
        return 2
    OUT = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="aether_e2e_ag_"))
    OUT.mkdir(parents=True, exist_ok=True)
    assert not any(OUT.iterdir()), "output dir must be empty"
    # Aether's own global state (last workspace pointer, registry) goes to the throw-away dir, never ~/.aether.
    (OUT / "aether_home").mkdir()
    os.environ["AETHER_DATA_DIR"] = str(OUT / "aether_home")
    home = Path.home()
    brain = home / ".gemini/antigravity/brain"
    dot_aether_before = listing(home / ".aether")
    brain_before = set(os.listdir(brain)) if brain.exists() else set()
    src_root = Path(__file__).resolve().parents[1] / "src"
    src_before = {p: m for p, m in listing(src_root).items() if "__pycache__" not in p}

    # 1. isolated project ------------------------------------------------------------------------------------
    proj = OUT / "project"
    proj.mkdir()
    (proj / "calc.py").write_text('def add(a, b):\n    """Return the sum of a and b."""\n    raise NotImplementedError\n', encoding="utf-8")
    (proj / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n"
        "    def test_ints(self): self.assertEqual(add(2, 3), 5)\n"
        "    def test_neg(self): self.assertEqual(add(-1, 1), 0)\n"
        "    def test_float(self): self.assertAlmostEqual(add(0.5, 0.25), 0.75)\n\n"
        "if __name__ == '__main__': unittest.main()\n", encoding="utf-8")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def git(*a):
        return subprocess.run(["git", "-c", "user.name=e2e", "-c", "user.email=e2e@example.invalid", *a], cwd=proj, capture_output=True, text=True)

    git("init", "-q"); git("add", "-A"); git("commit", "-qm", "initial stub")
    def unit():
        return subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=proj, capture_output=True, text=True, env=env)
    check("project_starts_clean", git("status", "--porcelain").stdout.strip() == "")
    check("tests_fail_before", unit().returncode != 0)
    head0 = git("rev-parse", "HEAD").stdout.strip()
    step("project_ready", head=head0[:8])

    # 2. workspace --------------------------------------------------------------------------------------------
    from aether.workspace.workspace import Workspace
    ws = Workspace.init(OUT / "ws", "E2E Antigravity")
    if not args.no_groq:
        real = home / "Library/Application Support/Aether/workspaces/try-aether-for-free"
        try:
            real_cfg = yaml.safe_load((real / "aether.yaml").read_text())
            from aether.core.secrets import get_secret_store
            key = get_secret_store(real / "data/vault/secrets.vault").get_secret("provider_api_key:groq")
            model = (real_cfg.get("workspace") or {}).get("default_model") or real_cfg.get("default_model")
            if key and model:
                os.environ["GROQ_API_KEY"] = key
                cfg = dict(ws.config); sec = dict(cfg.get("workspace") or {})
                sec.update(default_provider="groq", default_model=model); cfg["workspace"] = sec
                ws.config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8"); ws._config_cache = cfg
        except Exception as exc:
            print("Groq not configured for this run:", type(exc).__name__)
    from fastapi import Request
    from aether.server.app import app
    from aether.server.routes import (
        AcceptProposalPayload, CanonicalApprovalPayload, CodingRunTestsPayload, PersonalChatPayload,
        accept_proposal_route, approve_canonical_target_route, get_action_execution_route,
        personal_chat_route, request_coding_run_tests_route,
    )
    app.state.workspace = ws

    def mk(method="POST", path="/"):
        return Request({"type": "http", "method": method, "path": path, "headers": [], "app": app})

    step("workspace_ready", ws_id=ws.id, provider=(ws.config.get("workspace") or {}).get("default_provider"))

    async def flow():
        prompt = (f"Implementa la funzione add in {proj}/calc.py in modo che tutti i test in {proj}/test_calc.py passino. "
                  "Non modificare test_calc.py e non toccare altri file.")
        r1 = await personal_chat_route(mk(), PersonalChatPayload(prompt=prompt, workspace_id=ws.id, provider_id="antigravity"))
        prop = r1.get("proposal") or r1.get("metadata", {}).get("proposal")
        check("chat_creates_act_proposal", r1.get("tier") == "act" and bool(prop))
        r2 = await accept_proposal_route(mk(), proposal_id=prop["id"], payload=AcceptProposalPayload(actor="e2e_user"))
        authority = r2["authority"]
        check("consent_recorded", r2["status"] == "accepted" and authority["workspace_id"] == ws.id)
        r3 = await personal_chat_route(mk(), PersonalChatPayload(prompt=prompt, workspace_id=ws.id, authority=authority, provider_id="antigravity"))
        exec_id = r3.get("action_execution_id")
        st = await get_action_execution_route(mk("GET"), execution_id=exec_id)
        check("human_gate_before_run", st["status"] == "waiting_approval")
        step("approving_real_run", exec_id=exec_id)
        await approve_canonical_target_route(mk(), target_id=exec_id, payload=CanonicalApprovalPayload(actor="e2e_user"))
        st2 = await get_action_execution_route(mk("GET"), execution_id=exec_id)
        return exec_id, st2

    exec_id, st2 = asyncio.run(flow())
    out = st2.get("output_data") or {}
    action_rec = ws.actions.store.get_execution(exec_id)
    run_id = action_rec.metadata.get("coding_execution_id")
    run = ws.coding_runs.get_run(run_id) if run_id else None
    step("run_returned", exec_status=st2["status"], run_id=run_id, run_status=run.status.value if run else None,
         modified=out.get("modified_files"), verification=out.get("verification_passed"), error=str(st2.get("error_message") or "")[:300])
    new_convs = set(os.listdir(brain)) - brain_before
    check("exactly_one_new_antigravity_conversation", len(new_convs) == 1, str(sorted(new_convs)))
    check("run_attributed_to_antigravity_and_workspace", bool(run) and run.provider_id == "antigravity" and run.task.workspace_id == ws.id)
    events = [e["event"] for e in ws.coding_runs.list_events(run_id=run_id)] if run_id else []
    check("durable_events_recorded", "run_started" in events and any(e in events for e in ("run_completed", "run_failed", "run_timed_out")), str(events))

    mission_id = run.task.mission_id if run else None
    verified = bool(run and run.status.value == "completed" and run.result and run.result.verification_passed)
    if run and run.status.value in ("running", "waiting_for_interaction", "waiting_for_approval", "queued"):
        step("UNCERTAIN_REMOTE_STATE", run_status=run.status.value, note="not starting anything else; inspect Antigravity manually")
        (OUT / "report.json").write_text(json.dumps(REPORT, indent=2, default=str), encoding="utf-8")
        return 3

    # 3. authorised tests --------------------------------------------------------------------------------------
    if verified:
        async def tests_flow():
            r = await request_coding_run_tests_route(mk(), run_id, CodingRunTestsPayload())
            tid = r["action_execution_id"]
            await approve_canonical_target_route(mk(), target_id=tid, payload=CanonicalApprovalPayload(actor="e2e_user"))
            return await get_action_execution_route(mk("GET"), execution_id=tid)
        tr = asyncio.run(tests_flow())
        step("authorised_tests", status=tr["status"], passed=(tr.get("output_data") or {}).get("passed"))
        check("tests_ran_only_after_approval", tr["status"] == "succeeded")

    # 4. mission state from facts -------------------------------------------------------------------------------
    mission = ws.missions.get_mission(mission_id) if mission_id else None
    dels = ws.missions.list_deliverables(mission_id) if mission_id else []
    mems = ws.memory.list_memories(workspace_id=ws.id, mission_id=mission_id) if mission_id else []
    step("mission_state", mission=mission.status.value if mission else None,
         milestones=[m.status.value for m in mission.milestones] if mission else None,
         deliverables=[(d.name, d.status, d.sha256[:10] if d.sha256 else None) for d in dels],
         memories=[(m.summary[:60], m.provenance.verification_status) for m in mems])

    # 5. independent verification --------------------------------------------------------------------------------
    after_unit = unit()
    changed = [l[3:] for l in git("status", "--porcelain").stdout.splitlines() if "__pycache__" not in l]
    check("independent_unittest_passes", after_unit.returncode == 0, after_unit.stderr.strip().splitlines()[-1] if after_unit.stderr.strip() else "")
    check("only_calc_py_changed", changed == ["calc.py"], str(changed))
    check("test_file_untouched", git("diff", "--quiet", "--", "test_calc.py").returncode == 0)
    check("no_commit_or_push_by_agent", git("rev-parse", "HEAD").stdout.strip() == head0)
    if verified:
        check("mission_completed_only_with_evidence", bool(mission) and mission.status.value == "completed" and bool(dels) and all(d.status == "verified" for d in dels))
        check("verified_memory_written_once", len(mems) == 1 and mems[0].provenance.verification_status == "verified")
    else:
        check("mission_not_completed_without_evidence", bool(mission) and mission.status.value in ("failed", "waiting"))
        check("no_verified_deliverables_without_evidence", all(d.status != "verified" for d in dels))

    # 6. side effects ---------------------------------------------------------------------------------------------
    check("dot_aether_unchanged", listing(home / ".aether") == dot_aether_before)
    src_after = {p: m for p, m in listing(src_root).items() if "__pycache__" not in p}
    check("aether_source_untouched", src_after == src_before)
    step("done", failed_checks=[k for k, v in REPORT["checks"].items() if not v["ok"]])
    print(f"\nReport: {OUT / 'report.json'}")
    return 0 if all(v["ok"] for v in REPORT["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
