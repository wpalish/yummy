"""Structured logging, Sentry/OpenTelemetry hooks and Prometheus instruments."""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import sentry_sdk
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("yummy_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("yummy_http_request_duration_seconds", "HTTP latency", ["method", "route"],
                         buckets=(.01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10))
REDIS_FAILURES = Counter("yummy_redis_failures_total", "Redis operation failures")
DB_POOL_WAITING = Gauge("yummy_db_pool_requests_waiting", "PostgreSQL pool waiters")
PAYMENT_PENDING_AGE = Gauge("yummy_payment_pending_oldest_seconds", "Oldest pending payment age")
WEBHOOK_FAILURES = Gauge("yummy_webhook_failures", "Rejected/error webhook events")
REFUND_PENDING_AGE = Gauge("yummy_refund_pending_oldest_seconds", "Oldest pending refund age")
EMAIL_FAILURES = Gauge("yummy_email_delivery_failures", "Retry/dead notification count")
RESERVATION_EXPIRY = Counter("yummy_reservations_expired_total", "Expired payment reservations")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "event", "actor_id", "tenant_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    if os.getenv("YUMMY_JSON_LOGS", "1").lower() not in {"1", "true", "yes"}:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.getenv("YUMMY_LOG_LEVEL", "INFO").upper())


def configure_observability(app) -> None:
    configure_logging()
    dsn = os.getenv("SENTRY_DSN", "")
    if dsn:
        sentry_sdk.init(
            dsn=dsn, environment=os.getenv("YUMMY_ENV", "development"),
            release=os.getenv("YUMMY_RELEASE", "unknown"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
        )
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint:
        provider = TracerProvider(resource=Resource.create({"service.name": "yummy-api"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)


def observe_http(method: str, route: str, status: int, started: float) -> None:
    route = route or "unmatched"
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_LATENCY.labels(method, route).observe(time.monotonic() - started)


def record_redis_failure() -> None:
    REDIS_FAILURES.inc()
