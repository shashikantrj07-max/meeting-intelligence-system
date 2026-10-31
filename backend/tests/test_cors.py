from threading import Event

from fastapi.testclient import TestClient

from app.main import create_app


PRODUCTION_ORIGIN = "https://meeting-intelligence-system-rho.vercel.app"
LOCAL_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def _wait_for_shutdown(stop_event: Event) -> None:
    stop_event.wait()


def _preflight(origin: str, *, frontend_origin: str | None):
    app = create_app(frontend_origin, worker_runner=_wait_for_shutdown)
    with TestClient(app) as client:
        return client.options(
            "/api/meetings/00000000-0000-0000-0000-000000000001/insights",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "authorization,idempotency-key"
                ),
            },
        )


def _assert_allowed(response, origin: str) -> None:
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed_headers = {
        header.strip().lower()
        for header in response.headers["access-control-allow-headers"].split(",")
    }
    assert {"authorization", "idempotency-key"} <= allowed_headers


def _assert_rejected(response) -> None:
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_configured_production_origin_is_allowed() -> None:
    response = _preflight(PRODUCTION_ORIGIN, frontend_origin=PRODUCTION_ORIGIN)

    _assert_allowed(response, PRODUCTION_ORIGIN)


def test_local_origins_are_rejected_when_production_origin_is_configured() -> None:
    for origin in LOCAL_ORIGINS:
        _assert_rejected(
            _preflight(origin, frontend_origin=PRODUCTION_ORIGIN)
        )


def test_local_origins_are_allowed_when_production_origin_is_unset() -> None:
    for origin in LOCAL_ORIGINS:
        _assert_allowed(_preflight(origin, frontend_origin=None), origin)


def test_unrelated_origin_is_rejected_in_both_configurations() -> None:
    unrelated_origin = "https://unrelated.example"

    _assert_rejected(
        _preflight(unrelated_origin, frontend_origin=PRODUCTION_ORIGIN)
    )
    _assert_rejected(_preflight(unrelated_origin, frontend_origin=None))


def test_empty_production_origin_uses_local_development_origins() -> None:
    for origin in LOCAL_ORIGINS:
        _assert_allowed(_preflight(origin, frontend_origin=""), origin)
