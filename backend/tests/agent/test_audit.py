"""Tests for the audit logger.

Small surface, high stakes. The trail is the artefact that makes an autonomous
agent accountable, so what is checked here is that a row lands, that it lands in
the documented shape, and that everything from one pass is retrievable by one
trace id — the property the case-detail timeline is built on.
"""

from typing import Any

from app.agent import audit
from tests.agent.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase

CASE_ID = "33333333-3333-4333-8333-333333333333"
TRACE_ID = "trace0000000000000000000000000042"


def only_row(db: FakeSupabase) -> dict[str, Any]:
    rows = db.rows("audit_events")
    assert len(rows) == 1
    return rows[0]


async def test_log_agent_step_creates_row(db: FakeSupabase) -> None:
    event_id = await audit.log_agent_step(
        db,
        CASE_ID,
        MERCHANT_ID,
        "guardrail",
        "system",
        "guardrail_pass",
        {"verdict": "PASS"},
        TRACE_ID,
    )

    row = only_row(db)
    assert event_id == row["id"]
    assert row["case_id"] == CASE_ID
    assert row["merchant_id"] == MERCHANT_ID
    assert row["actor"] == "system"
    # `<step>:<label>` is the convention the audit page groups and filters on.
    assert row["event"] == "guardrail:guardrail_pass"
    assert row["details"] == {"verdict": "PASS"}
    assert row["trace_id"] == TRACE_ID


async def test_step_helpers_write_their_documented_subset(db: FakeSupabase) -> None:
    """A helper records the claim, not the whole model it was handed."""
    await audit.log_diagnosis(
        db,
        CASE_ID,
        MERCHANT_ID,
        {
            "root_cause": "salary_cycle_mismatch",
            "posterior_probability": 0.75,
            "causal_path": ["a", "b"],
            "is_stub": True,
            "supporting_evidence": ["this should not be copied into the trail"],
        },
        TRACE_ID,
    )

    row = only_row(db)
    assert row["event"] == "diagnose:diagnosis_complete"
    assert row["details"]["root_cause"] == "salary_cycle_mismatch"
    assert row["details"]["is_stub"] is True
    assert "supporting_evidence" not in row["details"]


async def test_guardrail_verdict_becomes_part_of_the_event_name(db: FakeSupabase) -> None:
    """`guardrail:guardrail_block` is filterable; a verdict buried in JSON is not."""
    await audit.log_guardrail(
        db,
        CASE_ID,
        MERCHANT_ID,
        {"verdict": "BLOCK", "checks": [], "blocking_check": "trai_quiet_hours"},
        TRACE_ID,
    )

    row = only_row(db)
    assert row["event"] == "guardrail:guardrail_block"
    assert row["details"]["blocking_check"] == "trai_quiet_hours"


async def test_trace_id_consistent_across_log_calls(db: FakeSupabase) -> None:
    """One pass, one trace id — the whole timeline is a single indexed lookup."""
    await audit.log_case_opened(db, CASE_ID, MERCHANT_ID, "failed_payment", 68000, TRACE_ID)
    await audit.log_uplift_verdict(
        db, CASE_ID, MERCHANT_ID, {"bucket": "persuadable", "verdict": "PROCEED"}, TRACE_ID
    )
    await audit.log_decision(
        db, CASE_ID, MERCHANT_ID, {"chosen_arm": "no_op", "alternatives_considered": []}, TRACE_ID
    )
    await audit.log_case_closed(db, CASE_ID, MERCHANT_ID, "stopped", "done", TRACE_ID)

    rows = db.rows("audit_events")
    assert len(rows) == 4
    assert {row["trace_id"] for row in rows} == {TRACE_ID}
    assert [row["event"] for row in rows] == [
        "detect:case_opened",
        "uplift_check:uplift_verdict",
        "decide:decision_made",
        "audit:case_closed",
    ]


async def test_log_agent_step_returns_empty_when_insert_returns_nothing() -> None:
    """A write that returns no row yields "" rather than raising into the loop."""

    class _Silent:
        def table(self, _name: str) -> "_Silent":
            return self

        def insert(self, _row: dict[str, Any]) -> "_Silent":
            return self

        def execute(self) -> Any:
            return type("R", (), {"data": []})()

    assert (
        await audit.log_agent_step(
            _Silent(), CASE_ID, MERCHANT_ID, "detect", "agent", "x", {}, TRACE_ID
        )
        == ""
    )
