"""Starting and reading a batch run.

The endpoint's job is to return before the work happens and to leave a row that
always describes the truth — including when the run falls over. A run stuck at
`running` is worse than a failed one: the screen shows a progress bar, and
nobody can tell a crash from work still in flight.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import simulator as module
from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from app.simulator.batch import MAX_CASES
from tests.simulator.conftest import MERCHANT_ID, OTHER_MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    fake.seed_merchant(OTHER_MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    monkeypatch.setattr(module, "get_service_client", lambda: db)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def start(client: TestClient, **body: Any) -> dict[str, Any]:
    payload = {"nCases": 100, "seed": 1}
    payload.update(body)
    response = client.post("/api/simulator/batch/start", json=payload)
    assert response.status_code == 202, response.text
    return response.json()


# ── Starting ───────────────────────────────────────────────────────────


def test_starting_returns_before_the_work_happens(client: TestClient, db: FakeSupabase) -> None:
    """202 rather than 200: accepted, not done."""
    body = start(client)

    assert body["status"] == "running"
    assert body["estimatedSeconds"] > 0
    assert len(db.rows("batch_runs")) == 1


def test_the_run_completes_and_records_its_result(client: TestClient, db: FakeSupabase) -> None:
    """`TestClient` drains background tasks before returning, so by here it is done."""
    batch_id = start(client)["batchId"]

    row = next(run for run in db.rows("batch_runs") if run["id"] == batch_id)
    assert row["status"] == "completed"
    assert row["completed_at"]
    assert row["result"]["total_cases"] == 100
    assert row["result"]["recovery_rate_by_policy"]["bandit"] > 0


def test_a_crashed_run_is_marked_failed_rather_than_left_running(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row stuck at `running` is a spinner nobody can clear.

    It reads as work still in progress, which is a worse failure than an error
    the screen can render.
    """

    async def explode(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulation fell over")

    monkeypatch.setattr(module, "run_batch", explode)

    batch_id = start(client)["batchId"]

    row = next(run for run in db.rows("batch_runs") if run["id"] == batch_id)
    assert row["status"] == "failed"
    assert "fell over" in row["error"]
    assert row["completed_at"]


@pytest.mark.parametrize("n", [49, MAX_CASES + 1])
def test_an_out_of_range_size_is_rejected(client: TestClient, n: int) -> None:
    assert client.post("/api/simulator/batch/start", json={"nCases": n}).status_code == 422


def test_an_unknown_playbook_in_the_mix_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/simulator/batch/start",
        json={"nCases": 100, "playbookDistribution": {"not_a_playbook": 1.0}},
    )

    assert response.status_code == 422
    assert "not_a_playbook" in response.json()["error"]["message"]


def test_a_distribution_need_not_sum_to_one(client: TestClient, db: FakeSupabase) -> None:
    """Weights are normalised — asking for 3:1 should not require thirds."""
    start(client, playbookDistribution={"failed_payment": 3, "b2b_overdue": 1})

    result = db.rows("batch_runs")[0]["result"]
    assert set(result["recovery_rate_by_playbook"]) <= {"failed_payment", "b2b_overdue"}


def test_an_all_zero_distribution_is_rejected_rather_than_dividing_by_zero(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/simulator/batch/start",
        json={"nCases": 100, "playbookDistribution": {"failed_payment": 0}},
    )

    assert response.status_code == 422


# ── Reading ────────────────────────────────────────────────────────────


def test_latest_returns_the_most_recent_run(client: TestClient, db: FakeSupabase) -> None:
    first = start(client)["batchId"]
    second = start(client, seed=2)["batchId"]

    body = client.get("/api/simulator/batch/latest").json()

    assert body["batchId"] == second
    assert body["batchId"] != first


def test_latest_does_not_skip_past_a_run_still_in_flight(
    client: TestClient, db: FakeSupabase
) -> None:
    """Showing the last completed run beside a progress bar for the one about to
    replace it would put stale numbers under a live heading."""
    start(client)
    db.rows("batch_runs").append(
        {
            "id": "in-flight",
            "merchant_id": MERCHANT_ID,
            "status": "running",
            "n_cases": 1000,
            "result": None,
            "started_at": "2099-01-01T00:00:00Z",
        }
    )

    assert client.get("/api/simulator/batch/latest").json()["batchId"] == "in-flight"


def test_latest_with_no_runs_is_a_404_not_an_empty_result(client: TestClient) -> None:
    """The empty state is a real state, and the page renders it differently."""
    assert client.get("/api/simulator/batch/latest").status_code == 404


def test_a_run_can_be_fetched_by_id(client: TestClient) -> None:
    batch_id = start(client)["batchId"]

    body = client.get(f"/api/simulator/batch/{batch_id}").json()

    assert body["batchId"] == batch_id
    assert body["status"] == "completed"


def test_an_unknown_id_is_a_404(client: TestClient) -> None:
    assert client.get("/api/simulator/batch/does-not-exist").status_code == 404


def test_the_literal_latest_path_is_not_read_as_an_id(client: TestClient) -> None:
    """Route order decides this, and getting it wrong 404s a valid request."""
    start(client)

    assert client.get("/api/simulator/batch/latest").status_code == 200


@pytest.mark.parametrize("path", ["/api/simulator/batch/latest", "/api/simulator/batch/some-id"])
def test_reads_require_authentication(path: str) -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as anonymous:
        assert anonymous.get(path).status_code in (401, 403)


def test_starting_requires_authentication() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as anonymous:
        response = anonymous.post("/api/simulator/batch/start", json={"nCases": 100})
        assert response.status_code in (401, 403)
