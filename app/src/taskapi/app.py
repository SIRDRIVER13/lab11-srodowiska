"""Task API: konfiguracja wyłącznie ze zmiennych środowiskowych (ConfigMap + Secret)."""
import json
import logging
import os
import socket
import sys
import time

import requests
from flask import Flask, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, create_engine, func, insert, select, text

APP_VERSION = os.getenv("APP_VERSION", "dev")

metadata = MetaData()
tasks = Table(
    "tasks", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(200), nullable=False),
    Column("done", Boolean, nullable=False, default=False),
)

REQUESTS = Counter("taskapi_http_requests_total", "Liczba zapytań HTTP", ["method", "endpoint", "status"])
LATENCY = Histogram("taskapi_http_request_seconds", "Czas obsługi zapytania", ["endpoint"])
INFO = Gauge("taskapi_info", "Informacje o wdrożeniu", ["environment", "version"])
TASKS = Gauge("taskapi_tasks_total", "Liczba zadań w bazie środowiska")


class JsonFormatter(logging.Formatter):
    """Logi w formacie JSON z nazwą środowiska - łatwe do rozdzielenia per środowisko."""

    def format(self, record):
        entry = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                 "env": os.getenv("APP_ENV", "local"), "msg": record.getMessage()}
        entry.update(getattr(record, "extra_fields", {}))
        return json.dumps(entry, ensure_ascii=False)


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("taskapi")
    log.handlers = [handler]
    log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    log.propagate = False
    return log


def database_url():
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return "postgresql+psycopg://{u}:{p}@{h}:{port}/{db}".format(
        u=os.environ["DB_USER"], p=os.environ["DB_PASSWORD"], h=os.environ["DB_HOST"],
        port=os.getenv("DB_PORT", "5432"), db=os.environ["DB_NAME"])


def mask(value):
    return f"{value[:2]}***" if value else "(brak)"


def create_app(db_url=None):
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.compact = False
    log = setup_logging()
    env = os.getenv("APP_ENV", "local")
    engine = create_engine(db_url or database_url(), pool_pre_ping=True)
    for attempt in range(10):  # baza może startować dłużej niż aplikacja
        try:
            metadata.create_all(engine)
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("Baza niedostępna (próba %s): %s", attempt + 1, exc)
            time.sleep(3)
    engine.dispose()
    INFO.labels(environment=env, version=APP_VERSION).set(1)

    @app.before_request
    def start_timer():
        g.start = time.perf_counter()

    @app.after_request
    def after(response):
        endpoint = request.url_rule.rule if request.url_rule else "unknown"
        if endpoint != "/metrics":
            REQUESTS.labels(request.method, endpoint, response.status_code).inc()
            LATENCY.labels(endpoint).observe(time.perf_counter() - g.start)
            fields = {"method": request.method, "path": request.path, "status": response.status_code}
            log.debug("request", extra={"extra_fields": fields})
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; form-action 'none'"
        response.headers["X-Environment"] = env
        return response

    @app.get("/")
    def index():
        return jsonify(app="Task API", environment=env, version=APP_VERSION, host=socket.gethostname())

    @app.get("/health")
    def health():
        if os.getenv("APP_BROKEN"):
            return jsonify(status="error", reason="APP_BROKEN", version=APP_VERSION), 503
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return jsonify(status="ok", database="ok", environment=env, version=APP_VERSION)

    @app.get("/config")
    def config():
        """Konfiguracja wczytana z ConfigMap/Secret - sekrety tylko zamaskowane."""
        return jsonify(
            environment=env,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            database={"host": os.getenv("DB_HOST", "-"), "name": os.getenv("DB_NAME", "-"),
                      "user": os.getenv("DB_USER", "-"), "password": mask(os.getenv("DB_PASSWORD", ""))},
            payment_api_url=os.getenv("PAYMENT_API_URL", "-"),
            payment_api_key=mask(os.getenv("PAYMENT_API_KEY", "")),
            feature_debug_endpoints=os.getenv("FEATURE_DEBUG", "false"),
        )

    @app.get("/tasks")
    def list_tasks():
        with engine.connect() as conn:
            rows = conn.execute(select(tasks).order_by(tasks.c.id)).mappings().all()
        return jsonify([dict(r) for r in rows])

    @app.post("/tasks")
    def create_task():
        data = request.get_json(silent=True) or {}
        title = str(data.get("title") or "").strip()
        if not title or len(title) > 200:
            return jsonify(error="Pole 'title' jest wymagane (1-200 znaków)"), 400
        with engine.begin() as conn:
            new_id = conn.execute(insert(tasks).values(title=title, done=False)).inserted_primary_key[0]
        log.info("Utworzono zadanie", extra={"extra_fields": {"task_id": new_id}})
        return jsonify(id=new_id, title=title, done=False, environment=env), 201

    @app.post("/pay")
    def pay():
        """Wywołanie zewnętrznej usługi płatności - endpoint zależny od środowiska."""
        url = os.getenv("PAYMENT_API_URL")
        if not url:
            return jsonify(error="Brak PAYMENT_API_URL"), 500
        try:
            resp = requests.post(f"{url}/charge", json={"amount": 100, "env": env},
                                 headers={"X-Api-Key": os.getenv("PAYMENT_API_KEY", "")}, timeout=3)
            return jsonify(endpoint=url, provider_response=resp.json()), resp.status_code
        except requests.RequestException as exc:
            log.error("Usługa płatności niedostępna: %s", exc)
            return jsonify(endpoint=url, error="Usługa płatności niedostępna"), 502

    @app.get("/metrics")
    def metrics():
        try:
            with engine.connect() as conn:
                TASKS.set(conn.execute(select(func.count()).select_from(tasks)).scalar())
        except Exception:  # noqa: BLE001
            pass
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    return app
