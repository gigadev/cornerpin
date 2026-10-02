from fastapi.testclient import TestClient

from cornerpin.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_lists_health() -> None:
    client = TestClient(create_app())

    schema = client.get("/openapi.json").json()

    assert "/v1/health" in schema["paths"]
