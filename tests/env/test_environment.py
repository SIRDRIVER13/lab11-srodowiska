"""Walidacja wdrożenia na środowisku. Na produkcji uruchamiane tylko testy oznaczone 'readonly'.

    BASE_URL=http://localhost:30111 EXPECTED_ENV=test pytest tests/env
    BASE_URL=http://localhost:30211 EXPECTED_ENV=production pytest tests/env -m readonly
"""
import os
import uuid

import pytest
import requests

DB_NAME = {"test": "taskapi_test", "production": "taskapi_prod"}
PAYMENT = {"test": "payments-sandbox", "production": "payments-live"}


@pytest.mark.readonly
def test_health_and_database(base_url, expected_env):
    body = requests.get(f"{base_url}/health", timeout=5).json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["environment"] == expected_env


@pytest.mark.readonly
def test_configuration_matches_environment(base_url, expected_env):
    cfg = requests.get(f"{base_url}/config", timeout=5).json()
    assert cfg["environment"] == expected_env
    assert cfg["database"]["name"] == DB_NAME[expected_env]
    assert PAYMENT[expected_env] in cfg["payment_api_url"]
    assert cfg["feature_debug_endpoints"] == ("true" if expected_env == "test" else "false")


@pytest.mark.readonly
def test_secrets_are_not_exposed(base_url):
    cfg = requests.get(f"{base_url}/config", timeout=5).json()
    assert cfg["database"]["password"].endswith("***")
    assert cfg["payment_api_key"].endswith("***")


@pytest.mark.readonly
def test_security_headers(base_url, expected_env):
    headers = requests.get(f"{base_url}/", timeout=5).headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Environment"] == expected_env


@pytest.mark.readonly
def test_metrics_endpoint(base_url, expected_env):
    metrics = requests.get(f"{base_url}/metrics", timeout=5).text
    assert f'taskapi_info{{environment="{expected_env}"' in metrics


def test_write_and_read_task(base_url):
    title = f"walidacja-{uuid.uuid4().hex[:8]}"
    assert requests.post(f"{base_url}/tasks", json={"title": title}, timeout=5).status_code == 201
    assert title in [t["title"] for t in requests.get(f"{base_url}/tasks", timeout=5).json()]


def test_payment_goes_to_sandbox(base_url, expected_env):
    if expected_env != "test":
        pytest.skip("płatność testowa tylko na środowisku testowym")
    body = requests.post(f"{base_url}/pay", timeout=10).json()
    assert body["provider_response"]["mode"] == "SANDBOX"
    assert body["provider_response"]["charged"] is False


def test_test_data_does_not_reach_production(base_url):
    prod = os.getenv("PROD_URL")
    if not prod:
        pytest.skip("PROD_URL nie ustawiony")
    try:
        requests.get(f"{prod}/health", timeout=3)
    except requests.RequestException:
        pytest.skip("środowisko PROD jeszcze nie istnieje (pierwsze wdrożenie)")
    title = f"izolacja-{uuid.uuid4().hex[:8]}"
    requests.post(f"{base_url}/tasks", json={"title": title}, timeout=5)
    assert title not in [t["title"] for t in requests.get(f"{prod}/tasks", timeout=5).json()]
