import logging

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlmodel import Session, SQLModel, select

from .config import ALLOWED_ORIGINS
from .db import engine, get_session
from .hub import hub
from .routers.admin import router as admin_router
from .routers.analytics import router as analytics_router
from .routers.customer import router as customer_router
from .routers.dev import router as dev_router
from .routers.menu import router as menu_router
from .routers.mobile import router as mobile_router
from .telemetry import (
    init_logging,
    new_request_id,
    observe_request,
    set_request_id,
    start_timer,
    ws_join,
    ws_leave,
)


init_logging()

app = FastAPI(title="FusionX Ordering + Truck Mobile API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


logger = logging.getLogger(__name__)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or new_request_id()
    set_request_id(request_id)
    started = start_timer()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request failure")
        response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
        status = 500
    else:
        status = response.status_code
    observe_request(request.method, request.url.path, status, started)
    response.headers["x-request-id"] = request_id
    return response


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


# Routers
app.include_router(mobile_router)
app.include_router(menu_router)
app.include_router(admin_router)
app.include_router(customer_router)
app.include_router(analytics_router)
app.include_router(dev_router)


@app.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
def readiness(session: Session = Depends(get_session)) -> dict:
    session.exec(select(1))
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.websocket("/api/mobile/ws/shift/{shift_id}")
async def ws_shift(ws: WebSocket, shift_id: int):
    request_id = new_request_id()
    set_request_id(request_id)
    await hub.join(shift_id, ws)
    ws_join(shift_id)
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        hub.leave(shift_id, ws)
    except Exception:
        hub.leave(shift_id, ws)
    finally:
        ws_leave(shift_id)
