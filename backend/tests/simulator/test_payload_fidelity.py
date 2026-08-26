"""The generated payloads must match the ones written in ``scenarios.md``.

``scenarios.md`` is the demo's contract: the video, the agent tests, and the
screenshots all assume the JSON in that file is what actually flows. This test
reads the fenced JSON blocks out of the document itself and compares them to
what the generators produce, so editing the script without editing the code (or
the reverse) fails the build instead of surfacing on stage.

Two of the six scripted blocks are abbreviated in the document — S5 and S6 show
only the fields their beat turns on, and elide ``merchant_id``/``currency`` that
every other block carries. Those are asserted as subsets. S1–S4 are complete and
are asserted as exact equality, key order included.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.simulator.scenarios import sample_payloads

#: tests/simulator/ -> tests/ -> backend/ -> repo root
SCENARIOS_MD = Path(__file__).resolve().parents[3] / "scenarios.md"

#: Blocks the document specifies in full; compared exactly.
COMPLETE = ["S1", "S2", "S3", "S4"]

#: Blocks the document abbreviates; compared as subsets.
ABBREVIATED = ["S5", "S6"]

_EVENT_TYPE_BY_CODE = {
    "S1": "subscription.charged.failed",
    "S2": "checkout.abandoned",
    "S3": "payment.failed",
    "S4": "invoice.overdue",
    "S5": "subscription.charged.failed",
    "S6": "payment.failed",
}

_CUSTOMER_BY_CODE = {
    "S1": "cust_suresh_iyer",
    "S2": "cust_priya_menon",
    "S3": "cust_aditya_rao",
    "S4": "cust_meera_rasoi_chain",
    "S5": "cust_vikram_sethi",
    "S6": "cust_sana_khatri",
}


def _documented_payloads() -> dict[str, dict[str, Any]]:
    """Every fenced JSON block in scenarios.md that is a trigger event.

    A trigger event is identified by carrying both an ``event`` key and the
    ``customer_id`` of the persona whose scenario it belongs to — which is
    enough to pick it out from the diagnosis and classification blocks that
    surround it, without depending on heading text or line numbers.
    """
    text = SCENARIOS_MD.read_text(encoding="utf-8")
    blocks: list[dict[str, Any]] = []
    for raw in re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # scenarios.md also contains illustrative pseudo-JSON.
            continue
        if isinstance(parsed, dict) and "event" in parsed and "customer_id" in parsed:
            blocks.append(parsed)

    by_code: dict[str, dict[str, Any]] = {}
    for code, customer in _CUSTOMER_BY_CODE.items():
        matches = [
            block
            for block in blocks
            if block.get("customer_id") == customer
            and block.get("event") == _EVENT_TYPE_BY_CODE[code]
        ]
        assert matches, f"No trigger-event JSON block found in scenarios.md for {code}"
        by_code[code] = matches[0]
    return by_code


def test_scenarios_md_is_readable() -> None:
    assert SCENARIOS_MD.exists(), f"scenarios.md not found at {SCENARIOS_MD}"
    assert len(_documented_payloads()) == 6


@pytest.mark.parametrize("code", COMPLETE)
def test_generated_payload_matches_the_script_exactly(code: str) -> None:
    documented = _documented_payloads()[code]
    generated = sample_payloads()[code]

    assert generated == documented
    # Key order too: the panel renders the payload verbatim, and a reader
    # comparing it against the script should not have to hunt for fields.
    assert list(generated) == list(documented)


@pytest.mark.parametrize("code", ABBREVIATED)
def test_generated_payload_contains_everything_the_script_states(code: str) -> None:
    documented = _documented_payloads()[code]
    generated = sample_payloads()[code]
    assert generated is not None

    for key, value in documented.items():
        assert key in generated, f"{code} payload is missing {key!r}"
        assert generated[key] == value, f"{code} payload disagrees on {key!r}"


@pytest.mark.parametrize("code", ABBREVIATED)
def test_abbreviated_payloads_only_add_the_boilerplate_fields(code: str) -> None:
    """The extra keys are the ones every other block carries — nothing invented."""
    documented = _documented_payloads()[code]
    generated = sample_payloads()[code]
    assert generated is not None

    extra = set(generated) - set(documented)
    boilerplate = {
        "merchant_id",
        "currency",
        "subscription_id",
        "method",
        "mandate_id",
        "bank",
        "order_id",
    }
    assert extra <= boilerplate


def test_batch_scenarios_have_no_payload() -> None:
    payloads = sample_payloads()
    assert payloads["B1"] is None
    assert payloads["B2"] is None


def test_b3_payload_is_an_sbi_upi_failure() -> None:
    payload = sample_payloads()["B3"]
    assert payload is not None
    assert payload["event"] == "payment.failed"
    assert payload["bank"] == "SBI"
    assert payload["method"] == "upi"
