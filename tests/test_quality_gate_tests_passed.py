"""
The technical rule ``tests_passed`` must be satisfied only by a coding run that itself COMPLETED and passed independent
verification, and only by a well-formed ``test_run`` (schema of ``coding.runs.run_authorised_tests``: ``passed``,
``exit_code``, ``timed_out``...). Runs that cannot prove anything are kept as ``context_runs`` to explain the outcome.
"""
from __future__ import annotations

import asyncio

import pytest

from aether.missions.models import Deliverable
from aether.missions.reviewer import QualityGateEvaluator

GOOD_TESTS = {"runner": "pytest", "exit_code": 0, "timed_out": False, "passed": True}


def _evaluate(tmp_path, runs, required=("tests_passed",)):
    report = tmp_path / "report.md"
    report.write_text("# Report\n\nContent.\n", encoding="utf-8")
    deliverables = [Deliverable(id="d1", mission_id="m1", name="report.md", path=str(report), type="document")]
    return asyncio.run(
        QualityGateEvaluator().evaluate(
            mission_title="T",
            mission_objective="Write a report",
            deliverables=deliverables,
            completed_context=["ok"],
            team=None,
            workspace=None,
            evidence={"coding_runs": runs},
            required_evidence=list(required) if required else None,
        )
    )


def _run(status="completed", verified=True, test_run=GOOD_TESTS, run_id="r1"):
    return {"id": run_id, "status": status, "verification_passed": verified, "test_run": test_run}


def test_completed_verified_run_with_passing_tests_satisfies_the_rule(tmp_path):
    ev = _evaluate(tmp_path, [_run()])
    assert ev.passed is True
    assert ev.semantically_verified is True
    assert [r["id"] for r in ev.evidence_used["coding_runs"]] == ["r1"]
    assert "context_runs" not in ev.evidence_used


def test_failed_run_with_an_inconsistent_positive_test_result_does_not_satisfy_the_rule(tmp_path):
    ev = _evaluate(tmp_path, [_run(status="failed", verified=False)])
    assert ev.passed is False
    assert ev.semantically_verified is False
    assert not ev.evidence_used.get("coding_runs")
    # the failed run is kept to EXPLAIN the failure, never as proof
    assert ev.evidence_used["context_runs"] == [{"id": "r1", "status": "failed", "verification_passed": False}]
    technical = ev.rules["technical_verification"]
    assert technical.passed is False and "r1[failed" in technical.reason


@pytest.mark.parametrize("status", ["running", "waiting_for_interaction", "requires_rework", "timed_out", "cancelled", "queued"])
def test_unfinished_or_unsuccessful_runs_never_satisfy_the_rule(tmp_path, status):
    ev = _evaluate(tmp_path, [_run(status=status, verified=True)])
    assert ev.passed is False
    assert not ev.evidence_used.get("coding_runs")


def test_completed_but_unverified_run_does_not_satisfy_the_rule(tmp_path):
    for verified in (False, None):
        ev = _evaluate(tmp_path, [_run(verified=verified)])
        assert ev.passed is False and not ev.evidence_used.get("coding_runs")


@pytest.mark.parametrize(
    "bad_run",
    [
        _run(test_run=None),
        _run(test_run={}),
        _run(test_run="passed"),
        _run(test_run={"passed": "true"}),  # truthy string is not the boolean True
        _run(test_run={"passed": 1}),
        _run(test_run={"passed": True, "exit_code": 1}),  # inconsistent with the runner's own exit code
        _run(test_run={"passed": True, "timed_out": True, "exit_code": 0}),
        _run(verified="true"),  # not the boolean True
        {"id": "no-status", "verification_passed": True, "test_run": GOOD_TESTS},
        "not-a-dict",
        None,
    ],
)
def test_missing_invalid_or_non_conforming_data_is_never_a_pass_and_never_raises(tmp_path, bad_run):
    ev = _evaluate(tmp_path, [bad_run])
    assert ev.passed is False
    assert ev.semantically_verified is False  # a failed gate never claims verification, whatever the run says


def test_a_failed_run_next_to_a_good_one_does_not_hide_the_good_one_and_is_still_reported(tmp_path):
    ev = _evaluate(tmp_path, [_run(status="failed", verified=False, run_id="bad"), _run(run_id="good")])
    assert ev.passed is True and ev.semantically_verified is True
    assert [r["id"] for r in ev.evidence_used["coding_runs"]] == ["good"]
    assert [r["id"] for r in ev.evidence_used["context_runs"]] == ["bad"]


def test_without_required_evidence_the_gate_behaves_as_before(tmp_path):
    ev = _evaluate(tmp_path, [_run(status="failed", verified=False)], required=None)
    assert ev.passed is True and ev.semantically_verified is False
