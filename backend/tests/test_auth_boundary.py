"""The authentication boundary on /api/merchants.

These assert the *rejection* paths, which need no database. The success paths
need a live Supabase project and are covered by the manual checklist in Phase 1.
"""

from fastapi.testclient import TestClient


def test_get_me_without_token_is_401(client: TestClient) -> None:
    response = client.get("/api/merchants/me")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Missing bearer token"


def test_get_me_with_garbage_token_is_401(client: TestClient) -> None:
    response = client.get(
        "/api/merchants/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid or expired token"


def test_patch_me_without_token_is_401(client: TestClient) -> None:
    response = client.patch("/api/merchants/me", json={"name": "Kajal & Co."})

    assert response.status_code == 401
