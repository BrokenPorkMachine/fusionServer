from typing import Dict, Set
from fastapi import WebSocket
from starlette.websockets import WebSocketState
import json

class Hub:
    def __init__(self):
        self.clients: Dict[int, Set[WebSocket]] = {}

    async def join(self, shift_id: int, ws: WebSocket):
        await ws.accept()
        self.clients.setdefault(shift_id, set()).add(ws)

    def leave(self, shift_id: int, ws: WebSocket):
        if shift_id in self.clients:
            self.clients[shift_id].discard(ws)

    async def emit(self, shift_id: int, event: dict):
        dead = []
        for ws in list(self.clients.get(shift_id, set())):
            try:
                if ws.application_state == WebSocketState.CONNECTED:
                    await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients[shift_id].discard(ws)

hub = Hub()
