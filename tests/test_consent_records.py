"""
Persistent consent: who authorised what, when, through which channel, for which proposal version and content.
Real PersonalStore/Workspace in temp dirs.
"""
from __future__ import annotations

import sqlite3

import pytest

from aether.core.execution import ExecutionBoundary, UnauthorizedExecutionError
from aether.planning.consent import ConsentRecord, proposal_digest
from aether.planning.contracts import ProposalStatus
from aether.workspace.workspace import Workspace
from conftest import make_test_accepted_authority


@pytest.fixture
def ws(tmp_path):
    w = Workspace.init(tmp_path / "ws", "Consent WS")
    yield w
    w.close()


def accepted(ws, constraints=None, **kw):
    return make_test_accepted_authority(ws, constraints=constraints or ["allow:probe.mutate", "allow_path:/tmp/allowed"], **kw)


def validate(ws, authority, action="probe.mutate", **kw):
    return ExecutionBoundary.validate_authority(authority=authority, workspace_id=ws.id, store=ws.personal_store,
                                                action_or_boundary=action, canonicalize=ws.canonical_id, **kw)


def test_acceptance_records_who_when_channel_scope_and_digest(ws):
    prop, auth = accepted(ws)
    c = ws.personal_store.get_consent(prop.id, prop.version)
    assert isinstance(c, ConsentRecord) and c.is_active
    assert (c.actor, c.actor_kind, c.channel) == ("user", "human", "api")
    assert c.workspace_id == ws.id and c.proposal_version == prop.version
    assert c.scope["allow"] == ["probe.mutate"] and c.scope["allow_paths"] == ["/tmp/allowed"]
    assert c.content_digest == proposal_digest(prop) and c.granted_at
    validate(ws, auth)  # a recorded consent makes the authority valid


def test_accepting_twice_keeps_a_single_consent_record(ws):
    prop, _ = accepted(ws)
    ws.personal.accept_proposal(prop.id, ws.id, actor="someone-else")
    consents = ws.personal_store.list_consents(ws.id)
    assert len(consents) == 1 and consents[0].actor == "user"   # the first, real decision is never overwritten


def test_autonomous_consent_is_marked_as_policy_not_human(ws):
    prop, auth = accepted(ws)
    # a second proposal accepted by the policy engine
    import uuid
    from datetime import datetime, timezone
    from aether.planning.contracts import IntentRequest, MissionProposal
    store = ws.personal_store
    store.save_intent_request(IntentRequest(id="int-auto", workspace_id=ws.id, raw_input="x", source_surface="t",
                                            created_at=datetime.now(timezone.utc).isoformat(), constraints=["allow:probe.mutate"]))
    p2 = MissionProposal(id="prop-auto", intent_id="int-auto", workspace_id=ws.id, title="t", objective="o", why="w",
                         context_summary="c", confidence=1.0, constraints=["allow:probe.mutate"], status=ProposalStatus.READY_FOR_ACCEPTANCE)
    store.save_proposal(p2)
    ws.personal.accept_proposal("prop-auto", ws.id, actor="system_autonomous", channel="policy", policy_code="AUTO_AUTONOMOUS")
    c = store.get_consent("prop-auto", 1)
    assert (c.actor_kind, c.channel, c.policy_code) == ("policy_autonomous", "policy", "AUTO_AUTONOMOUS")


def test_revoking_consent_kills_every_authority_derived_from_it(ws):
    prop, auth = accepted(ws)
    validate(ws, auth)
    ws.personal.revoke_proposal(prop.id, ws.id, actor="user", reason="changed my mind")
    with pytest.raises(UnauthorizedExecutionError):
        validate(ws, auth)
    c = ws.personal_store.get_consent(prop.id, prop.version)
    assert not c.is_active and "changed my mind" in c.revoke_reason


def test_proposal_edited_after_consent_invalidates_it(ws):
    prop, auth = accepted(ws)
    validate(ws, auth)
    conn = sqlite3.connect(ws.personal_db_path)
    conn.execute("UPDATE mission_proposals SET constraints = ? WHERE id = ?", ('["allow:*"]', prop.id))  # silently widened
    conn.commit(); conn.close()
    ws.personal_store.close() if hasattr(ws.personal_store, "close") and False else None
    with pytest.raises(UnauthorizedExecutionError) as e:
        validate(ws, auth)
    assert "modified after consent" in str(e.value)


def test_accepted_status_without_a_consent_record_is_not_enough(ws):
    prop, auth = accepted(ws)
    conn = sqlite3.connect(ws.personal_db_path)
    conn.execute("DELETE FROM proposal_consents WHERE proposal_id = ?", (prop.id,))
    conn.commit(); conn.close()
    with pytest.raises(UnauthorizedExecutionError) as e:
        validate(ws, auth)
    assert "no recorded consent" in str(e.value)


def test_legacy_backfill_marks_old_acceptances_as_legacy_and_is_idempotent(ws):
    prop, auth = accepted(ws)
    conn = sqlite3.connect(ws.personal_db_path)
    conn.execute("DELETE FROM proposal_consents WHERE proposal_id = ?", (prop.id,))   # as if accepted before consents existed
    conn.commit(); conn.close()
    assert ws.personal_store.backfill_legacy_consents() == 1
    c = ws.personal_store.get_consent(prop.id, prop.version)
    assert (c.actor, c.actor_kind, c.channel) == ("legacy_unknown", "legacy", "migration")
    validate(ws, auth)
    assert ws.personal_store.backfill_legacy_consents() == 0


@pytest.mark.asyncio
async def test_route_cannot_be_used_to_forge_an_autonomous_consent(ws):
    from types import SimpleNamespace
    from aether.server.routes import AcceptProposalPayload, accept_proposal_route
    import uuid
    from datetime import datetime, timezone
    from aether.planning.contracts import IntentRequest, MissionProposal
    store = ws.personal_store
    store.save_intent_request(IntentRequest(id="int-r", workspace_id=ws.id, raw_input="x", source_surface="t",
                                            created_at=datetime.now(timezone.utc).isoformat(), constraints=["allow:probe.mutate"]))
    store.save_proposal(MissionProposal(id="prop-r", intent_id="int-r", workspace_id=ws.id, title="t", objective="o", why="w",
                                        context_summary="c", confidence=1.0, constraints=["allow:probe.mutate"],
                                        status=ProposalStatus.READY_FOR_ACCEPTANCE))
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(workspace=ws)))
    await accept_proposal_route(req, "prop-r", AcceptProposalPayload(actor="system_autonomous"))
    c = store.get_consent("prop-r", 1)
    assert c.actor_kind == "human" and c.actor == "user:system_autonomous" and c.channel == "api"


def test_consent_revocation_alone_invalidates_an_otherwise_accepted_proposal(ws):
    prop, auth = accepted(ws)
    assert ws.personal_store.revoke_consent(prop.id, prop.version, "audit: withdrawn")
    assert ws.personal_store.get_proposal(prop.id).status == ProposalStatus.ACCEPTED   # status untouched
    with pytest.raises(UnauthorizedExecutionError) as e:
        validate(ws, auth)
    assert "revoked" in str(e.value)
