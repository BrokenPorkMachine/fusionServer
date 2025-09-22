from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from .db import engine
from .config import ALLOWED_ORIGINS
from .hub import hub
from .routers.mobile import router as mobile_router
from .routers.dev import router as dev_router

app = FastAPI(title="FusionX Ordering + Truck Mobile API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

# Routers
app.include_router(mobile_router)
app.include_router(dev_router)

# WebSocket for mobile (TruckKDS) already exposed in mobile router via /api/mobile/ws/shift/{id} on separate server earlier
# We can also add a plain echo for diagnostics if needed.

@app.websocket("/api/mobile/ws/shift/{shift_id}")
async def ws_shift(ws: WebSocket, shift_id: int):
    await hub.join(shift_id, ws)
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        hub.leave(shift_id, ws)
    except Exception:
        hub.leave(shift_id, ws)
