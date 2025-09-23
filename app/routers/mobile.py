from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import hash_pw, make_token, require_auth
from ..db import get_session
from ..hub import hub
from ..models import (
    AuditLog,
    Device,
    InventoryAdjustment,
    Location,
    MenuCategory,
    MenuItem,
    NotificationChannel,
    Order,
    OrderItem,
    OrderState,
    Staff,
    Truck,
    TruckMenuItem,
    TruckShift,
    ShiftStatus,
)
from ..services.notifications import notification_service
from ..utils.async_helpers import fire_and_forget


router = APIRouter(prefix="/api/mobile", tags=["mobile"])


def _record_audit(
    session: Session,
    staff: Staff,
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    metadata: Optional[dict] = None,
) -> None:
    session.add(
        AuditLog(
            staff_id=staff.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=json.dumps(metadata or {}),
        )
    )


def _ensure_truck_menu_item(session: Session, shift_id: int, menu_item: MenuItem) -> TruckMenuItem:
    tmi = session.exec(
        select(TruckMenuItem).where(
            TruckMenuItem.shift_id == shift_id,
            TruckMenuItem.menu_item_id == menu_item.id,
            TruckMenuItem.is_special == False,
        )
    ).first()
    if not tmi:
        tmi = TruckMenuItem(shift_id=shift_id, menu_item_id=menu_item.id)
        session.add(tmi)
        session.commit()
        session.refresh(tmi)
    return tmi


def _menu_entry(
    tmi: TruckMenuItem,
    base: Optional[MenuItem],
    categories: Dict[int, MenuCategory],
) -> dict:
    category_id = tmi.category_id or (base.category_id if base else None)
    category_name = (
        categories[category_id].name if category_id and category_id in categories else None
    )
    price = (
        tmi.price_override_cents
        if tmi.price_override_cents is not None
        else base.base_price_cents if base else 0
    )
    return {
        "menuItemId": base.id if base else None,
        "truckMenuItemId": tmi.id,
        "name": tmi.display_name or (base.name if base else tmi.display_name or ""),
        "description": tmi.display_description or (base.description if base else ""),
        "priceCents": price,
        "stockCount": tmi.stock_count,
        "outOfStock": tmi.out_of_stock,
        "category": category_name,
        "isSpecial": tmi.is_special,
        "displayOrder": tmi.display_order
        if tmi.display_order is not None
        else (base.sort_order if base else 0),
        "availableStart": tmi.available_start or (base.available_start if base else None),
        "availableEnd": tmi.available_end or (base.available_end if base else None),
    }


class LoginResponse(BaseModel):
    token: str
    staff: Dict[str, Any]


@router.post("/login", response_model=LoginResponse)
def mobile_login(
    payload: Dict[str, str] = Body(...), session: Session = Depends(get_session)
):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    st = session.exec(select(Staff).where(Staff.username == username)).first()
    if not st or st.password_hash != hash_pw(password):
        raise HTTPException(status_code=401, detail="Bad credentials")
    tok = make_token(st)
    return LoginResponse(
        token=tok,
        staff={"id": st.id, "name": st.name, "role": st.role},
    )


@router.post("/devices/register", status_code=204)
def register_device(
    payload: Dict[str, str] = Body(...),
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    token = payload.get("apns_token")
    if not token:
        raise HTTPException(400, "apns_token required")
    dev = session.exec(
        select(Device).where(Device.apns_token == token, Device.staff_id == staff.id)
    ).first()
    now = datetime.now(timezone.utc)
    if not dev:
        dev = Device(
            staff_id=staff.id,
            apns_token=token,
            platform=payload.get("platform", "ios"),
            app_version=payload.get("app_version", "0"),
            os_version=payload.get("os_version", "unknown"),
            last_seen_at=now,
        )
    else:
        dev.platform = payload.get("platform", dev.platform)
        dev.app_version = payload.get("app_version", dev.app_version)
        dev.os_version = payload.get("os_version", dev.os_version)
        dev.last_seen_at = now
        dev.revoked_at = None
    session.add(dev)
    session.commit()
    return JSONResponse(status_code=204, content=None)


@router.post("/devices/heartbeat", status_code=204)
def device_heartbeat(
    payload: Dict[str, str] = Body(...),
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    token = payload.get("apns_token") or payload.get("device_token")
    dev_id = payload.get("device_id")
    query = select(Device).where(Device.staff_id == staff.id)
    if token:
        query = query.where(Device.apns_token == token)
    elif dev_id:
        try:
            dev_id_int = int(dev_id)
        except (TypeError, ValueError):
            raise HTTPException(400, "device_id must be an integer")
        query = query.where(Device.id == dev_id_int)
    else:
        raise HTTPException(400, "apns_token or device_id required")
    dev = session.exec(query).first()
    if not dev:
        raise HTTPException(404, "device not found")
    if dev.revoked_at:
        raise HTTPException(403, "device revoked")
    dev.last_seen_at = datetime.now(timezone.utc)
    session.add(dev)
    session.commit()
    return JSONResponse(status_code=204, content=None)


class DeviceOut(BaseModel):
    id: int
    platform: str
    appVersion: str
    osVersion: str
    lastSeenAt: Optional[datetime]


@router.get("/devices", response_model=List[DeviceOut])
def list_devices(
    staff: Staff = Depends(require_auth), session: Session = Depends(get_session)
):
    devices = session.exec(
        select(Device).where(Device.staff_id == staff.id, Device.revoked_at.is_(None))
    ).all()
    return [
        DeviceOut(
            id=dev.id,
            platform=dev.platform,
            appVersion=dev.app_version,
            osVersion=dev.os_version,
            lastSeenAt=dev.last_seen_at,
        )
        for dev in devices
    ]


@router.delete("/devices/{device_id}", status_code=204)
def revoke_device(
    device_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    dev = session.exec(
        select(Device).where(Device.id == device_id, Device.staff_id == staff.id)
    ).first()
    if not dev:
        raise HTTPException(404, "device not found")
    dev.revoked_at = datetime.now(timezone.utc)
    session.add(dev)
    session.commit()
    return JSONResponse(status_code=204, content=None)


@router.get("/shift/active")
def active_shift(
    staff: Staff = Depends(require_auth), session: Session = Depends(get_session)
):
    if not staff.truck_id:
        return {}
    sh = session.exec(
        select(TruckShift)
        .where(
            TruckShift.truck_id == staff.truck_id,
            TruckShift.status != ShiftStatus.CHECKED_OUT,
        )
        .order_by(TruckShift.id.desc())
    ).first()
    return sh or {}


@router.post("/shift/checkin")
def checkin(
    payload: Dict[str, int] = Body(...),
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    truck_id = payload.get("truck_id") or staff.truck_id
    location_id = payload.get("location_id")
    if not truck_id or not location_id:
        raise HTTPException(400, "truck_id and location_id required")
    loc = session.get(Location, location_id)
    if not loc:
        raise HTTPException(404, "location not found")
    for prev in session.exec(
        select(TruckShift).where(
            TruckShift.truck_id == truck_id,
            TruckShift.status != ShiftStatus.CHECKED_OUT,
        )
    ).all():
        prev.status = ShiftStatus.CHECKED_OUT
        prev.ends_at = datetime.now(timezone.utc)
        session.add(prev)
    shift = TruckShift(
        truck_id=truck_id,
        location_id=location_id,
        status=ShiftStatus.CHECKED_IN,
        lat=loc.lat,
        lon=loc.lon,
    )
    session.add(shift)
    session.commit()
    session.refresh(shift)
    _record_audit(
        session,
        staff,
        "checkin",
        "TruckShift",
        shift.id,
        {"truck_id": truck_id, "location_id": location_id},
    )
    session.commit()
    return {
        "id": shift.id,
        "truck_id": shift.truck_id,
        "location_id": shift.location_id,
        "status": shift.status,
        "starts_at": shift.starts_at,
    }


@router.post("/shift/{shift_id}/checkout", status_code=204)
def checkout(
    shift_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    sh = session.get(TruckShift, shift_id)
    if not sh:
        raise HTTPException(404, "shift not found")
    sh.status = ShiftStatus.CHECKED_OUT
    sh.ends_at = datetime.now(timezone.utc)
    session.add(sh)
    _record_audit(session, staff, "checkout", "TruckShift", shift_id, None)
    session.commit()
    fire_and_forget(hub.emit(shift_id, {"event": "resume"}))
    return JSONResponse(status_code=204, content=None)


@router.post("/shift/{shift_id}/pause")
def pause_shift(
    shift_id: int,
    payload: Dict[str, Any] = Body(...),
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    minutes = int(payload.get("minutes") or 10)
    reason = payload.get("reason") or "Paused"
    sh = session.get(TruckShift, shift_id)
    if not sh:
        raise HTTPException(404, "shift not found")
    if sh.status == ShiftStatus.CHECKED_OUT:
        raise HTTPException(400, "shift checked out")
    sh.status = ShiftStatus.PAUSED
    sh.resume_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    session.add(sh)
    _record_audit(session, staff, "pause", "TruckShift", shift_id, {"minutes": minutes})
    session.commit()
    fire_and_forget(hub.emit(shift_id, {"event": "pause", "reason": reason}))
    return {"status": sh.status, "resume_at": sh.resume_at}


@router.post("/shift/{shift_id}/resume")
def resume_shift(
    shift_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    sh = session.get(TruckShift, shift_id)
    if not sh:
        raise HTTPException(404, "shift not found")
    if sh.status == ShiftStatus.CHECKED_OUT:
        raise HTTPException(400, "shift checked out")
    sh.status = ShiftStatus.CHECKED_IN
    sh.resume_at = None
    session.add(sh)
    _record_audit(session, staff, "resume", "TruckShift", shift_id, None)
    session.commit()
    fire_and_forget(hub.emit(shift_id, {"event": "resume"}))
    return {"status": sh.status}


class ShiftConfig(BaseModel):
    throttlePer5Min: int
    slotCapacityPerMin: int


class ShiftConfigPayload(BaseModel):
    throttlePer5Min: Optional[int] = Field(default=None, ge=1)
    slotCapacityPerMin: Optional[int] = Field(default=None, ge=1)


def _shift_to_config(shift: TruckShift) -> ShiftConfig:
    return ShiftConfig(
        throttlePer5Min=shift.throttle_per_5m,
        slotCapacityPerMin=shift.slot_capacity_per_min,
    )


@router.get("/shift/{shift_id}/config", response_model=ShiftConfig)
def get_shift_config(
    shift_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    sh = session.get(TruckShift, shift_id)
    if not sh:
        raise HTTPException(404, "shift not found")
    return _shift_to_config(sh)


@router.patch("/shift/{shift_id}/config", response_model=ShiftConfig)
def update_shift_config(
    shift_id: int,
    payload: ShiftConfigPayload,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    sh = session.get(TruckShift, shift_id)
    if not sh:
        raise HTTPException(404, "shift not found")
    if payload.throttlePer5Min is None and payload.slotCapacityPerMin is None:
        raise HTTPException(400, "No configuration changes provided")
    if payload.throttlePer5Min is not None:
        sh.throttle_per_5m = payload.throttlePer5Min
    if payload.slotCapacityPerMin is not None:
        sh.slot_capacity_per_min = payload.slotCapacityPerMin
    session.add(sh)
    _record_audit(
        session,
        staff,
        "update_config",
        "TruckShift",
        shift_id,
        payload.model_dump(exclude_unset=True),
    )
    session.commit()
    fire_and_forget(hub.emit(shift_id, {"event": "config_updated"}))
    return _shift_to_config(sh)


class TruckInfo(BaseModel):
    id: int
    name: str
    capacity: int
    tz: str


class TruckEnvelope(BaseModel):
    trucks: List[TruckInfo]


@router.get("/trucks", response_model=TruckEnvelope)
def list_trucks(
    staff: Staff = Depends(require_auth), session: Session = Depends(get_session)
):
    query = select(Truck).where(Truck.active == True)  # noqa: E712
    if staff.truck_id:
        query = query.where(Truck.id == staff.truck_id)
    trucks = session.exec(query.order_by(Truck.name.asc())).all()
    return {
        "trucks": [
            TruckInfo(id=t.id, name=t.name, capacity=t.capacity, tz=t.tz)
            for t in trucks
        ]
    }


class LocationInfo(BaseModel):
    id: int
    name: str
    address: str
    lat: float
    lon: float
    taxRegion: str
    geofenceMeters: int


class LocationEnvelope(BaseModel):
    locations: List[LocationInfo]


@router.get("/locations", response_model=LocationEnvelope)
def list_locations(
    _staff: Staff = Depends(require_auth), session: Session = Depends(get_session)
):
    locations = session.exec(select(Location).order_by(Location.name.asc())).all()
    return {
        "locations": [
            LocationInfo(
                id=loc.id,
                name=loc.name,
                address=loc.address,
                lat=loc.lat,
                lon=loc.lon,
                taxRegion=loc.tax_region,
                geofenceMeters=loc.geofence_m,
            )
            for loc in locations
        ]
    }


class MenuEnvelope(BaseModel):
    items: List[Dict[str, Any]]


@router.get("/shift/{shift_id}/menu", response_model=MenuEnvelope)
def shift_menu(
    shift_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    shift = session.get(TruckShift, shift_id)
    if not shift:
        raise HTTPException(404, "shift not found")
    categories = {c.id: c for c in session.exec(select(MenuCategory)).all()}
    items: List[Dict[str, Any]] = []
    base_items = session.exec(select(MenuItem).where(MenuItem.is_active == True)).all()
    now = datetime.now(timezone.utc)
    for base in base_items:
        tmi = _ensure_truck_menu_item(session, shift_id, base)
        start = tmi.available_start or base.available_start
        end = tmi.available_end or base.available_end
        if start and start > now:
            continue
        if end and end < now:
            continue
        if not tmi.visible:
            continue
        items.append(_menu_entry(tmi, base, categories))
    specials = session.exec(
        select(TruckMenuItem)
        .where(TruckMenuItem.shift_id == shift_id, TruckMenuItem.is_special == True)
        .order_by(TruckMenuItem.display_order.asc())
    ).all()
    for spec in specials:
        if spec.available_start and spec.available_start > now:
            continue
        if spec.available_end and spec.available_end < now:
            continue
        if not spec.visible:
            continue
        items.append(_menu_entry(spec, None, categories))
    items.sort(key=lambda itm: ((itm.get("category") or ""), itm.get("displayOrder"), itm["name"]))
    return {"items": items}


class InventoryUpdate(BaseModel):
    menuItemId: Optional[int] = None
    truckMenuItemId: Optional[int] = None
    stockCount: Optional[int] = None
    outOfStock: Optional[bool] = None


class InventoryPayload(BaseModel):
    updates: List[InventoryUpdate]


@router.patch("/shift/{shift_id}/inventory", status_code=204)
def update_inventory(
    shift_id: int,
    payload: InventoryPayload,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    shift = session.get(TruckShift, shift_id)
    if not shift:
        raise HTTPException(404, "shift not found")
    low_stock_items: List[TruckMenuItem] = []
    for upd in payload.updates:
        tmi = None
        if upd.truckMenuItemId:
            tmi = session.get(TruckMenuItem, upd.truckMenuItemId)
        elif upd.menuItemId:
            tmi = session.exec(
                select(TruckMenuItem).where(
                    TruckMenuItem.shift_id == shift_id,
                    TruckMenuItem.menu_item_id == upd.menuItemId,
                )
            ).first()
        if not tmi:
            raise HTTPException(404, "menu item not found for shift")
        if upd.stockCount is not None:
            new_stock = max(0, upd.stockCount)
            previous = tmi.stock_count or 0
            tmi.stock_count = new_stock
            tmi.last_stock_update_at = datetime.now(timezone.utc)
            delta = new_stock - previous
            if delta != 0:
                session.add(
                    InventoryAdjustment(
                        shift_id=shift_id,
                        truck_menu_item_id=tmi.id,
                        menu_item_id=tmi.menu_item_id,
                        delta=delta,
                        reason="manual_adjustment",
                        staff_id=staff.id,
                    )
                )
        if upd.outOfStock is not None:
            tmi.out_of_stock = bool(upd.outOfStock)
        session.add(tmi)
        threshold = tmi.low_stock_threshold or 0
        if tmi.out_of_stock or (tmi.stock_count is not None and tmi.stock_count <= threshold):
            low_stock_items.append(tmi)
    session.commit()
    for tmi in low_stock_items:
        base = session.get(MenuItem, tmi.menu_item_id) if tmi.menu_item_id else None
        name = tmi.display_name or (base.name if base else "Item")
        fire_and_forget(
            hub.emit(shift_id, {"event": "low_stock", "menu_item_id": tmi.menu_item_id or tmi.id})
        )
        notification_service.notify_low_stock(session, shift=shift, menu_item_name=name)
    return JSONResponse(status_code=204, content=None)


class TicketItem(BaseModel):
    name: str
    qty: int
    mods: List[str] = []


class KDSTicket(BaseModel):
    order_id: int
    created_at: datetime
    state: str
    on_hold_until: Optional[datetime]
    hold_reason: Optional[str]
    items: List[TicketItem]


class TicketEnvelope(BaseModel):
    tickets: List[KDSTicket]


@router.get("/shift/{shift_id}/kds", response_model=TicketEnvelope)
def kds(
    shift_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    orders = session.exec(
        select(Order)
        .where(
            Order.shift_id == shift_id,
            Order.state.in_(
                [
                    OrderState.NEW,
                    OrderState.PAID,
                    OrderState.IN_QUEUE,
                    OrderState.IN_PROGRESS,
                    OrderState.ON_HOLD,
                    OrderState.READY,
                ]
            ),
        )
        .order_by(Order.created_at.asc())
    ).all()
    tickets: List[KDSTicket] = []
    for o in orders:
        items = session.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all()
        tickets.append(
            KDSTicket(
                order_id=o.id,
                created_at=o.created_at,
                state=o.state,
                on_hold_until=o.on_hold_until,
                hold_reason=o.hold_reason,
                items=[
                    TicketItem(
                        name=it.name,
                        qty=it.qty,
                        mods=json.loads(it.modifiers_json or "[]"),
                    )
                    for it in items
                ],
            )
        )
    return {"tickets": tickets}


class AdvancePayload(BaseModel):
    to: str


ALLOWED_ADVANCES = {
    OrderState.PAID: [OrderState.IN_QUEUE, OrderState.IN_PROGRESS],
    OrderState.IN_QUEUE: [OrderState.IN_PROGRESS, OrderState.ON_HOLD],
    OrderState.IN_PROGRESS: [OrderState.READY, OrderState.ON_HOLD],
    OrderState.ON_HOLD: [OrderState.IN_PROGRESS, OrderState.IN_QUEUE],
    OrderState.READY: [OrderState.PICKED_UP],
}


@router.post("/order/{order_id}/advance")
def advance(
    order_id: int,
    payload: AdvancePayload,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    o = session.get(Order, order_id)
    if not o:
        raise HTTPException(404, "order not found")
    allowed = ALLOWED_ADVANCES.get(o.state, [])
    if payload.to not in allowed:
        raise HTTPException(400, f"Cannot advance from {o.state} to {payload.to}")
    o.previous_state = o.state
    o.state = payload.to
    o.last_state_change_at = datetime.now(timezone.utc)
    if payload.to == OrderState.READY:
        o.prep_completed_at = datetime.now(timezone.utc)
    if payload.to != OrderState.ON_HOLD:
        o.on_hold_until = None
        o.hold_reason = None
    session.add(o)
    _record_audit(session, staff, "advance", "Order", order_id, {"to": payload.to})
    session.commit()
    fire_and_forget(hub.emit(o.shift_id, {"event": "order_advanced", "order_id": o.id}))
    return {"state": o.state}


class OrderDetailItem(BaseModel):
    name: str
    qty: int
    priceCents: int
    modifiers: List[str]


class OrderDetail(BaseModel):
    orderId: int
    state: str
    customerName: Optional[str]
    customerPhone: Optional[str]
    items: List[OrderDetailItem]
    holdReason: Optional[str]
    onHoldUntil: Optional[datetime]


@router.get("/order/{order_id}", response_model=OrderDetail)
def order_detail(
    order_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    items = session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    return OrderDetail(
        orderId=order.id,
        state=order.state,
        customerName=order.customer_name,
        customerPhone=order.customer_phone,
        items=[
            OrderDetailItem(
                name=item.name,
                qty=item.qty,
                priceCents=item.price_cents,
                modifiers=json.loads(item.modifiers_json or "[]"),
            )
            for item in items
        ],
        holdReason=order.hold_reason,
        onHoldUntil=order.on_hold_until,
    )


class HoldPayload(BaseModel):
    minutes: int = Field(default=15, ge=1)
    reason: str = "On hold"


@router.post("/order/{order_id}/hold")
def hold_order(
    order_id: int,
    payload: HoldPayload,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    if order.state not in {OrderState.IN_QUEUE, OrderState.IN_PROGRESS}:
        raise HTTPException(400, "Only active orders can be held")
    order.previous_state = order.state
    order.state = OrderState.ON_HOLD
    order.on_hold_until = datetime.now(timezone.utc) + timedelta(minutes=payload.minutes)
    order.hold_reason = payload.reason
    order.last_state_change_at = datetime.now(timezone.utc)
    session.add(order)
    _record_audit(
        session,
        staff,
        "hold",
        "Order",
        order_id,
        payload.model_dump(),
    )
    session.commit()
    fire_and_forget(hub.emit(order.shift_id, {"event": "order_hold", "order_id": order.id}))
    return {"state": order.state, "on_hold_until": order.on_hold_until}


@router.post("/order/{order_id}/resume")
def resume_order(
    order_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    if order.state != OrderState.ON_HOLD:
        raise HTTPException(400, "Order not on hold")
    order.state = order.previous_state or OrderState.IN_QUEUE
    order.previous_state = None
    order.on_hold_until = None
    order.hold_reason = None
    order.last_state_change_at = datetime.now(timezone.utc)
    session.add(order)
    _record_audit(session, staff, "resume", "Order", order_id, None)
    session.commit()
    fire_and_forget(hub.emit(order.shift_id, {"event": "order_resume", "order_id": order.id}))
    return {"state": order.state}


class CancelPayload(BaseModel):
    reason: str
    refund: bool = False
    refundReason: Optional[str] = None


@router.post("/order/{order_id}/cancel")
def cancel_order(
    order_id: int,
    payload: CancelPayload,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    if order.state in {OrderState.PICKED_UP, OrderState.CANCELED, OrderState.REFUNDED}:
        raise HTTPException(400, "Order already closed")
    order.previous_state = order.state
    order.cancellation_reason = payload.reason
    order.canceled_at = datetime.now(timezone.utc)
    order.last_state_change_at = datetime.now(timezone.utc)
    if payload.refund:
        order.state = OrderState.REFUNDED
        order.refund_reason = payload.refundReason or payload.reason
        order.refunded_at = datetime.now(timezone.utc)
    else:
        order.state = OrderState.CANCELED
    session.add(order)
    _record_audit(
        session,
        staff,
        "cancel",
        "Order",
        order_id,
        payload.model_dump(),
    )
    session.commit()
    fire_and_forget(hub.emit(order.shift_id, {"event": "order_cancel", "order_id": order.id}))
    return {"state": order.state}


class BulkAdvancePayload(BaseModel):
    orderIds: List[int]


@router.post("/shift/{shift_id}/advance-ready")
def bulk_advance_ready(
    shift_id: int,
    payload: BulkAdvancePayload,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    if not payload.orderIds:
        raise HTTPException(400, "orderIds required")
    updated = 0
    now = datetime.now(timezone.utc)
    for order in session.exec(
        select(Order).where(Order.id.in_(payload.orderIds), Order.shift_id == shift_id)
    ).all():
        if order.state == OrderState.READY:
            order.state = OrderState.PICKED_UP
            order.last_state_change_at = now
            updated += 1
            session.add(order)
    session.commit()
    if updated:
        fire_and_forget(hub.emit(shift_id, {"event": "bulk_advance", "count": updated}))
    _record_audit(
        session,
        staff,
        "bulk_advance",
        "TruckShift",
        shift_id,
        {"orders": payload.orderIds, "updated": updated},
    )
    session.commit()
    return {"updated": updated}


class ShiftSummary(BaseModel):
    shiftId: int
    status: str
    startedAt: datetime
    endedAt: Optional[datetime]
    totalOrders: int
    revenueCents: int
    ordersByState: Dict[str, int]
    averagePrepSeconds: Optional[int]
    canceledCount: int
    refundedCount: int


@router.get("/shift/{shift_id}/summary", response_model=ShiftSummary)
def shift_summary(
    shift_id: int,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    sh = session.get(TruckShift, shift_id)
    if not sh:
        raise HTTPException(404, "shift not found")
    orders = session.exec(select(Order).where(Order.shift_id == shift_id)).all()
    revenue = 0
    orders_by_state: Dict[str, int] = {}
    prep_durations: List[float] = []
    canceled = 0
    refunded = 0
    for order in orders:
        revenue += order.total_cents
        orders_by_state[order.state] = orders_by_state.get(order.state, 0) + 1
        if order.prep_completed_at:
            duration = (order.prep_completed_at - order.created_at).total_seconds()
            if duration >= 0:
                prep_durations.append(duration)
        if order.state == OrderState.CANCELED:
            canceled += 1
        if order.state == OrderState.REFUNDED:
            refunded += 1
    avg_prep = int(sum(prep_durations) / len(prep_durations)) if prep_durations else None
    return ShiftSummary(
        shiftId=shift_id,
        status=sh.status,
        startedAt=sh.starts_at,
        endedAt=sh.ends_at,
        totalOrders=len(orders),
        revenueCents=revenue,
        ordersByState=orders_by_state,
        averagePrepSeconds=avg_prep,
        canceledCount=canceled,
        refundedCount=refunded,
    )


class StaffProfilePayload(BaseModel):
    phoneNumber: Optional[str] = None
    preferredChannel: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6)


@router.patch("/staff/profile")
def update_staff_profile(
    payload: StaffProfilePayload,
    staff: Staff = Depends(require_auth),
    session: Session = Depends(get_session),
):
    changed: Dict[str, Any] = {}
    if payload.phoneNumber is not None:
        staff.phone_number = payload.phoneNumber
        changed["phone_number"] = payload.phoneNumber
    if payload.preferredChannel is not None:
        if payload.preferredChannel not in {
            NotificationChannel.PUSH,
            NotificationChannel.SMS,
            NotificationChannel.EMAIL,
        }:
            raise HTTPException(400, "Unsupported channel")
        staff.preferred_notification_channel = payload.preferredChannel
        changed["preferred_notification_channel"] = payload.preferredChannel
    if payload.password is not None:
        staff.password_hash = hash_pw(payload.password)
        changed["password"] = True
    session.add(staff)
    if changed:
        _record_audit(session, staff, "update_profile", "Staff", staff.id, changed)
    session.commit()
    return {
        "id": staff.id,
        "name": staff.name,
        "phoneNumber": staff.phone_number,
        "preferredChannel": staff.preferred_notification_channel,
    }
