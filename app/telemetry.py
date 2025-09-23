import logging
import time
import uuid
from contextvars import ContextVar

from prometheus_client import Counter, Gauge, Histogram


_request_id_ctx: ContextVar[str] = ContextVar("fusionx_request_id", default="-")


REQUEST_COUNTER = Counter(
    "fusionx_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "fusionx_request_latency_seconds",
    "Latency for HTTP requests",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
WS_CONNECTIONS = Gauge(
    "fusionx_ws_connections", "Active websocket connections", ["shift_id"]
)


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str:
    return _request_id_ctx.get()


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.request_id = get_request_id()
        return True


def init_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def start_timer() -> float:
    return time.perf_counter()


def observe_request(method: str, path: str, status_code: int, started: float) -> None:
    duration = time.perf_counter() - started
    REQUEST_COUNTER.labels(method, path, str(status_code)).inc()
    REQUEST_LATENCY.labels(method, path).observe(duration)


def new_request_id() -> str:
    return str(uuid.uuid4())


def ws_join(shift_id: int) -> None:
    WS_CONNECTIONS.labels(str(shift_id)).inc()


def ws_leave(shift_id: int) -> None:
    WS_CONNECTIONS.labels(str(shift_id)).dec()
