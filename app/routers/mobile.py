from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import asyncio, json

from ..db import get_session
from ..auth import require_auth, make_token, hash_pw
from ..models import (
    Staff, Device, TruckShift, ShiftStatus,
    Location, MenuItem, TruckMenuItem,
    Order, OrderItem, OrderState
)
from ..hub import hub

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

@router.post("/login")
def mobile_login(payload: Dict[str, str] = Body(...), session: Session = Depends(get_session)):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    st = session.exec(select(Staff).where(Staff.username == username)).first()
    if not st or st.password_hash != hash_pw(password):
        raise HTTPException(status_code=401, detail="Bad credentials")
    tok = make_token(st)
    return {"token": tok, "staff": {"id": st.id, "name": st.name, "role": st.role}}

@router.post("/devices/register", status_code=204)
def register_device(payload: Dict[str, str] = Body(...), staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    token = payload.get("apns_token")
    if not token:
        raise HTTPException(400, "apns_token required")
    dev = session.exec(select(Device).where(Device.apns_token == token, Device.staff_id == staff.id)).first()
    if not dev:
        dev = Device(staff_id=staff.id, apns_token=token, platform=payload.get("platform","ios"), app_version=payload.get("app_version","0"))
        session.add(dev)
        session.commit()
    return JSONResponse(status_code=204, content=None)

@router.get("/shift/active")
def active_shift(staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    if not staff.truck_id:
        return {}
    sh = session.exec(select(TruckShift)
        .where(TruckShift.truck_id == staff.truck_id, TruckShift.status != ShiftStatus.CHECKED_OUT)
        .order_by(TruckShift.id.desc())
    ).first()
    return sh or {}

@router.post("/shift/checkin")
def checkin(payload: Dict[str, int] = Body(...), staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    truck_id = payload.get("truck_id") or staff.truck_id
    location_id = payload.get("location_id")
    if not truck_id or not location_id:
        raise HTTPException(400, "truck_id and location_id required")
    loc = session.get(Location, location_id)
    if not loc:
        raise HTTPException(404, "location not found")
    for prev in session.exec(select(TruckShift).where(TruckShift.truck_id == truck_id, TruckShift.status != ShiftStatus.CHECKED_OUT)).all():
        prev.status = ShiftStatus.CHECKED_OUT
        prev.ends_at = datetime.now(timezone.utc)
        session.add(prev)
    shift = TruckShift(truck_id=truck_id, location_id=location_id, status=ShiftStatus.CHECKED_IN, lat=loc.lat, lon=loc.lon)
    session.add(shift); session.commit(); session.refresh(shift)
    return shift

@router.post("/shift/{shift_id}/checkout", status_code=204)
def checkout(shift_id: int, staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    sh = session.get(TruckShift, shift_id)
    if not sh: raise HTTPException(404, "shift not found")
    sh.status = ShiftStatus.CHECKED_OUT; sh.ends_at = datetime.now(timezone.utc)
    session.add(sh); session.commit()
    asyncio.create_task(hub.emit(shift_id, {"event":"resume"}))
    return JSONResponse(status_code=204, content=None)

@router.post("/shift/{shift_id}/pause")
def pause_shift(shift_id: int, payload: Dict[str, Any] = Body(...), staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    minutes = int(payload.get("minutes") or 10); reason = payload.get("reason") or "Paused"
    sh = session.get(TruckShift, shift_id)
    if not sh: raise HTTPException(404, "shift not found")
    if sh.status == ShiftStatus.CHECKED_OUT: raise HTTPException(400, "shift checked out")
    sh.status = ShiftStatus.PAUSED; sh.resume_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    session.add(sh); session.commit()
    asyncio.create_task(hub.emit(shift_id, {"event":"pause", "reason": reason}))
    return {"status": sh.status, "resume_at": sh.resume_at}

@router.post("/shift/{shift_id}/resume")
def resume_shift(shift_id: int, staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    sh = session.get(TruckShift, shift_id)
    if not sh: raise HTTPException(404, "shift not found")
    if sh.status == ShiftStatus.CHECKED_OUT: raise HTTPException(400, "shift checked out")
    sh.status = ShiftStatus.CHECKED_IN; sh.resume_at = None
    session.add(sh); session.commit()
    asyncio.create_task(hub.emit(shift_id, {"event":"resume"}))
    return {"status": sh.status}

# Menu & Inventory
from pydantic import BaseModel

class MenuEnvelope(BaseModel):
    items: List[dict]

@router.get("/shift/{shift_id}/menu", response_model=MenuEnvelope)
def shift_menu(shift_id: int, staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    base = session.exec(select(MenuItem)).all()
    out: List[dict] = []
    for m in base:
        tmi = session.exec(select(TruckMenuItem).where(TruckMenuItem.shift_id == shift_id, TruckMenuItem.menu_item_id == m.id)).first()
        if not tmi:
            tmi = TruckMenuItem(shift_id=shift_id, menu_item_id=m.id); session.add(tmi); session.commit(); session.refresh(tmi)
        price = tmi.price_override_cents if tmi.price_override_cents is not None else m.base_price_cents
        out.append({"id": m.id, "name": m.name, "priceCents": price, "stockCount": tmi.stock_count, "outOfStock": tmi.out_of_stock})
    return {"items": out}

class InventoryUpdate(BaseModel):
    menu_item_id: int
    stock_count: Optional[int] = None
    out_of_stock: Optional[bool] = None

class InventoryPayload(BaseModel):
    updates: List[InventoryUpdate]

@router.patch("/shift/{shift_id}/inventory", status_code=204)
def update_inventory(shift_id: int, payload: InventoryPayload, staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    lows: List[int] = []
    for upd in payload.updates:
        tmi = session.exec(select(TruckMenuItem).where(TruckMenuItem.shift_id == shift_id, TruckMenuItem.menu_item_id == upd.menu_item_id)).first()
        if not tmi:
            tmi = TruckMenuItem(shift_id=shift_id, menu_item_id=upd.menu_item_id); session.add(tmi); session.commit(); session.refresh(tmi)
        if upd.stock_count is not None: tmi.stock_count = max(0, upd.stock_count)
        if upd.out_of_stock is not None: tmi.out_of_stock = bool(upd.out_of_stock)
        session.add(tmi); session.commit()
        if tmi.stock_count is not None and tmi.stock_count <= (tmi.low_stock_threshold or 0):
            lows.append(upd.menu_item_id)
    for mid in lows:
        asyncio.create_task(hub.emit(shift_id, {"event":"low_stock", "menu_item_id": mid}))
    return JSONResponse(status_code=204, content=None)

# KDS
class TicketItem(BaseModel):
    name: str; qty: int; mods: List[str] = []

class KDSTicket(BaseModel):
    order_id: int; created_at: datetime; state: str; items: List[TicketItem]

class TicketEnvelope(BaseModel):
    tickets: List[KDSTicket]

@router.get("/shift/{shift_id}/kds", response_model=TicketEnvelope)
def kds(shift_id: int, staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    orders = session.exec(select(Order)
        .where(Order.shift_id == shift_id, Order.state.in_([
            OrderState.NEW, OrderState.PAID, OrderState.IN_QUEUE, OrderState.IN_PROGRESS, OrderState.READY
        ])).order_by(Order.created_at.asc())
    ).all()
    tickets: List[KDSTicket] = []
    for o in orders:
        items = session.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all()
        tickets.append(KDSTicket(order_id=o.id, created_at=o.created_at, state=o.state,
            items=[TicketItem(name=it.name, qty=it.qty, mods=json.loads(it.modifiers_json or "[]")) for it in items]))
    return {"tickets": tickets}

class AdvancePayload(BaseModel):
    to: str

ALLOWED_ADVANCES = {
    OrderState.PAID: [OrderState.IN_QUEUE, OrderState.IN_PROGRESS],
    OrderState.IN_QUEUE: [OrderState.IN_PROGRESS],
    OrderState.IN_PROGRESS: [OrderState.READY],
    OrderState.READY: [OrderState.PICKED_UP],
}

@router.post("/order/{order_id}/advance")
def advance(order_id: int, payload: AdvancePayload, staff: Staff = Depends(require_auth), session: Session = Depends(get_session)):
    o = session.get(Order, order_id)
    if not o: raise HTTPException(404, "order not found")
    allowed = ALLOWED_ADVANCES.get(o.state, [])
    if payload.to not in allowed: raise HTTPException(400, f"Cannot advance from {o.state} to {payload.to}")
    o.state = payload.to; session.add(o); session.commit()
    asyncio.create_task(hub.emit(o.shift_id, {"event":"new_order", "order_id": o.id}))
    return {"state": o.state}
