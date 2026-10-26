import os

import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:30111")
EXPECTED_ENV = os.getenv("EXPECTED_ENV", "test")


@pytest.fixture()
def base_url():
    return BASE_URL


@pytest.fixture()
def expected_env():
    return EXPECTED_ENV


def pytest_configure(config):
    config.addinivalue_line("markers", "readonly: test bez zapisu danych - bezpieczny dla produkcji")
