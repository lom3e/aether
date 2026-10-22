"""
Frontend contract for approval answers. The UI must never present an approval as a completed job unless the backend says
the action finished. The pure logic lives in ``ui/src/approvalOutcome.ts`` (no imports), executed here with Node's native
TypeScript support; a source-level guard checks that the client uses the canonical route (the legacy
``/api/actions/executions/{id}/approve`` route returns only the bare entity: no success/status/message).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

UI_SRC = Path(__file__).resolve().parent.parent / "ui" / "src"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required to execute the TypeScript helper")

CASES = [
    # decision, response, finished, in_progress, toast
    ("approve", {"success": True, "status": "approved", "entity": {"status": "succeeded", "output_data": {}}}, True, False, "success"),
    ("approve", {"success": True, "status": "already_completed", "entity": {}}, True, False, "info"),
    ("approve", {"success": True, "status": "in_progress", "entity": {"status": "running"}}, False, True, "info"),
    ("approve", {"success": True, "status": "approved", "entity": {"output_data": {"run_terminal": False}}}, False, True, "success"),
    ("approve", {"success": False, "status": "failed", "entity": {"status": "failed"}}, False, False, "error"),
    ("approve", {"success": False, "status": "not_executed"}, False, False, "error"),
    ("approve", {"success": True, "status": "unauthorized"}, False, False, "error"),
    ("reject", {"success": True, "status": "rejected"}, False, False, "info"),
    ("reject", {"success": True, "status": "already_completed"}, True, False, "info"),
    ("reject", {"success": False, "status": "not_executed"}, False, False, "error"),
]

SCRIPT = """
import * as m from %s;
const cases = JSON.parse(process.argv[1]);
const out = cases.map(([decision, res]) => ({
  finished: m.approvalIsFinished(res),
  inProgress: m.approvalIsInProgress(res),
  toast: m.approvalToastKind(res, decision),
}));
const msgs = {
  approve_failed: m.defaultApprovalMessage('approve', 'failed'),
  approve_progress: m.defaultApprovalMessage('approve', 'in_progress'),
  approve_default: m.defaultApprovalMessage('approve', 'approved'),
  reject: m.defaultApprovalMessage('reject', 'rejected'),
};
console.log(JSON.stringify({ out, msgs }));
"""


def _run_helper():
    module = json.dumps((UI_SRC / "approvalOutcome.ts").as_uri())
    result = subprocess.run(
        [NODE, "--experimental-strip-types", "--input-type=module", "-e", SCRIPT % module, json.dumps([[c[0], c[1]] for c in CASES])],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def helper_output():
    return _run_helper()


@pytest.mark.parametrize("index", range(len(CASES)))
def test_outcomes_never_claim_more_than_the_backend_reported(helper_output, index):
    _, response, finished, in_progress, toast = CASES[index]
    got = helper_output["out"][index]
    assert got == {"finished": finished, "inProgress": in_progress, "toast": toast}, response


def test_fallback_messages_never_claim_execution(helper_output):
    msgs = helper_output["msgs"]
    assert "executed" not in msgs["approve_default"].lower() and "executed" not in msgs["approve_progress"].lower()
    assert "failed" in msgs["approve_failed"] and "in progress" in msgs["approve_progress"]


def test_client_uses_the_canonical_route_and_the_backend_success_flag():
    source = (UI_SRC / "canonicalNotification.ts").read_text(encoding="utf-8")
    body = source[source.index("export async function submitApprovalDecision"):]
    assert "/api/actions/executions/" not in body, "legacy route returns no success/status/message"
    assert "/api/approvals/" in body
    assert re.search(r"success:\s*data\.success\s*!==\s*false", body), "success must come from the backend answer"
    assert "approved and executed" not in body, "the client must not invent an 'executed' message"


def test_components_do_not_hardcode_success_toasts_for_approvals():
    for name in ("Home.tsx", "companion/useCompanionRuntime.ts", "NotificationCenter.tsx", "ConnectionsAdvanced.tsx"):
        text = (UI_SRC / name).read_text(encoding="utf-8")
        assert "approvalToastKind" in text, f"{name} must derive the toast kind from the outcome"
        assert not re.search(r"showToast\([^)]*,\s*['\"]success['\"]\)", "\n".join(
            line for line in text.splitlines() if "approve" in line.lower() and "res.message" in line
        )), f"{name} still shows a hardcoded success toast for an approval"
