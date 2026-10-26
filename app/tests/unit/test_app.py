import pytest

from taskapi.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "unit")
    monkeypatch.setenv("DB_PASSWORD", "tajnehaslo123")
    monkeypatch.setenv("PAYMENT_API_KEY", "sk_test_abcdef")
    return create_app(f"sqlite:///{tmp_path}/t.db").test_client()


def test_index_reports_environment(client):
    assert client.get("/").get_json()["environment"] == "unit"


def test_health(client):
    assert client.get("/health").get_json()["status"] == "ok"


def test_config_masks_secrets(client):
    body = client.get("/config").get_json()
    assert body["database"]["password"] == "ta***"
    assert body["payment_api_key"] == "sk***"
    assert "tajnehaslo123" not in str(body)


def test_tasks_flow_and_validation(client):
    assert client.post("/tasks", json={"title": "Zadanie"}).status_code == 201
    assert client.post("/tasks", json={}).status_code == 400
    assert client.get("/tasks").get_json()[0]["title"] == "Zadanie"


def test_metrics_and_headers(client):
    client.get("/")
    resp = client.get("/metrics")
    assert b"taskapi_http_requests_total" in resp.data
    assert b'taskapi_info{environment="unit"' in resp.data
    assert resp.headers["X-Environment"] == "unit"


def test_broken_version(client, monkeypatch):
    monkeypatch.setenv("APP_BROKEN", "1")
    assert client.get("/health").status_code == 503
