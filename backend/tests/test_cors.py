from fastapi.testclient import TestClient

from app.main import app


def test_job_enqueue_cors_preflight_allows_idempotency_key() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/meetings/00000000-0000-0000-0000-000000000001/insights",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "authorization,idempotency-key"
                ),
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:3000"
    )
    allowed_headers = {
        header.strip().lower()
        for header in response.headers["access-control-allow-headers"].split(",")
    }
    assert {"authorization", "idempotency-key"} <= allowed_headers
