"""Loading, reloading, and resetting the persona fixture set."""

from fastapi.testclient import TestClient

from app.simulator import fixtures
from tests.simulator.conftest import MERCHANT_ID, rows
from tests.simulator.fake_supabase import FakeSupabase


def test_load_fixtures_creates_six_personas(client: TestClient, db: FakeSupabase) -> None:
    response = client.post("/api/simulator/fixtures/load")

    assert response.status_code == 200, response.text
    customers = rows(db, "customers", merchant_id=MERCHANT_ID)
    external_ids = {row["external_id"] for row in customers}

    for persona in fixtures.ALL_PERSONAS:
        assert persona["external_id"] in external_ids

    scripted = [row for row in customers if row["external_id"] in fixtures.PERSONA_BY_ID]
    assert len(scripted) == 6


def test_load_fixtures_also_loads_the_b3_cohort(client: TestClient, db: FakeSupabase) -> None:
    client.post("/api/simulator/fixtures/load")

    cohort = [
        row
        for row in rows(db, "customers", merchant_id=MERCHANT_ID)
        if row["external_id"].startswith("cust_b3_downtime_")
    ]
    assert len(cohort) == 8


def test_load_fixtures_creates_every_payment_method(client: TestClient, db: FakeSupabase) -> None:
    response = client.post("/api/simulator/fixtures/load")

    # Eight across the six scripted personas, plus one UPI method each for the
    # eight B3 customers.
    expected = fixtures.TOTAL_PAYMENT_METHODS + len(fixtures.B3_SYNTHETIC_CUSTOMERS)
    assert fixtures.TOTAL_PAYMENT_METHODS == 8
    assert response.json()["loaded"]["paymentMethods"] == expected
    assert db.count("payment_methods") == expected


def test_load_fixtures_is_idempotent(client: TestClient, db: FakeSupabase) -> None:
    client.post("/api/simulator/fixtures/load")
    first = db.count("customers")
    first_methods = db.count("payment_methods")

    client.post("/api/simulator/fixtures/load")

    assert db.count("customers") == first
    # Methods are rewritten, not appended — a fixture edit has to take effect.
    assert db.count("payment_methods") == first_methods


def test_load_fixtures_stamps_rows_as_simulator_created(
    client: TestClient, db: FakeSupabase
) -> None:
    client.post("/api/simulator/fixtures/load")

    for row in rows(db, "customers", merchant_id=MERCHANT_ID):
        assert row["metadata"]["is_simulator_fixture"] is True


def test_load_fixtures_writes_an_audit_row(client: TestClient, db: FakeSupabase) -> None:
    client.post("/api/simulator/fixtures/load")

    audit = rows(db, "audit_events", merchant_id=MERCHANT_ID, event="fixtures_loaded")
    assert len(audit) == 1
    assert audit[0]["actor"] == "system"


def test_fixture_status_reports_loaded(loaded_client: TestClient) -> None:
    body = loaded_client.get("/api/simulator/fixtures/status").json()

    assert body["loaded"] is True
    assert sorted(body["personas"]) == sorted(p["name"] for p in fixtures.ALL_PERSONAS)
    assert body["counts"]["customers"] == 14


def test_fixture_status_reports_not_loaded_before_a_load(client: TestClient) -> None:
    body = client.get("/api/simulator/fixtures/status").json()

    assert body["loaded"] is False
    assert body["counts"]["customers"] == 0
    # The scenario catalogue is available whether or not fixtures are loaded —
    # the panel has to render the dropdown before you can load anything.
    assert len(body["scenarios"]) == 9


def test_reset_fixtures_deletes_only_simulator_data(
    loaded_client: TestClient, db: FakeSupabase
) -> None:
    # A customer the merchant added themselves, carrying no fixture stamp.
    db.insert_row(
        "customers",
        {
            "merchant_id": MERCHANT_ID,
            "external_id": "cust_merchants_own",
            "name": "Real Customer",
            "metadata": {},
        },
    )
    loaded_client.post("/api/simulator/scenarios/S1")

    response = loaded_client.post("/api/simulator/fixtures/reset")

    assert response.status_code == 200, response.text
    survivors = rows(db, "customers", merchant_id=MERCHANT_ID)
    assert [row["external_id"] for row in survivors] == ["cust_merchants_own"]
    assert rows(db, "recovery_cases", merchant_id=MERCHANT_ID) == []
    assert rows(db, "events", merchant_id=MERCHANT_ID) == []
    assert db.count("payment_methods") == 0


def test_reset_leaves_a_trail_of_its_own(loaded_client: TestClient, db: FakeSupabase) -> None:
    loaded_client.post("/api/simulator/fixtures/reset")

    audit = rows(db, "audit_events", merchant_id=MERCHANT_ID, event="fixtures_reset")
    assert len(audit) == 1
    assert audit[0]["actor"] == "system"
