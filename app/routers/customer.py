from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import require_roles
from ..db import get_session
from ..hub import hub
from ..models import (
    InventoryAdjustment,
    LoyaltyLedger,
    MenuCategory,
    MenuItem,
    Order,
    OrderItem,
    OrderState,
    Staff,
    StaffRole,
    TruckMenuItem,
    TruckShift,
)
from ..services.notifications import notification_service
from ..utils.async_helpers import fire_and_forget


router = APIRouter(prefix="/api/customer", tags=["customer"])


def _ensure_truck_menu_item(
    session: Session, shift_id: int, menu_item: MenuItem
) -> TruckMenuItem:
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


class CustomerMenuItem(BaseModel):
    truckMenuItemId: int
    name: str
    description: str
    priceCents: int
    stockCount: Optional[int]
    outOfStock: bool
    category: Optional[str]
    isSpecial: bool


class CustomerMenuEnvelope(BaseModel):
    items: List[CustomerMenuItem]


@router.get("/menu/{shift_id}", response_model=CustomerMenuEnvelope)
def customer_menu(shift_id: int, session: Session = Depends(get_session)):
    shift = session.get(TruckShift, shift_id)
    if not shift:
        raise HTTPException(404, "Shift not found")
    now = datetime.now(timezone.utc)
    items: List[CustomerMenuItem] = []
    categories = {c.id: c for c in session.exec(select(MenuCategory)).all()}
    base_items = session.exec(select(MenuItem).where(MenuItem.is_active == True)).all()
    for base in base_items:
        tmi = _ensure_truck_menu_item(session, shift_id, base)
        if not tmi.visible:
            continue
        start = tmi.available_start or base.available_start
        end = tmi.available_end or base.available_end
        if start and start > now:
            continue
        if end and end < now:
            continue
        cat_id = tmi.category_id or base.category_id
        category_name = categories[cat_id].name if cat_id and cat_id in categories else None
        price = (
            tmi.price_override_cents
            if tmi.price_override_cents is not None
            else base.base_price_cents
        )
        items.append(
            CustomerMenuItem(
                truckMenuItemId=tmi.id,
                name=tmi.display_name or base.name,
                description=tmi.display_description or base.description,
                priceCents=price,
                stockCount=tmi.stock_count,
                outOfStock=tmi.out_of_stock,
                category=category_name,
                isSpecial=False,
            )
        )
    specials = session.exec(
        select(TruckMenuItem)
        .where(TruckMenuItem.shift_id == shift_id, TruckMenuItem.is_special == True)
        .order_by(TruckMenuItem.display_order.asc())
    ).all()
    for spec in specials:
        if not spec.visible:
            continue
        if spec.available_start and spec.available_start > now:
            continue
        if spec.available_end and spec.available_end < now:
            continue
        price = spec.price_override_cents or 0
        cat_id = spec.category_id
        category_name = categories[cat_id].name if cat_id and cat_id in categories else None
        items.append(
            CustomerMenuItem(
                truckMenuItemId=spec.id,
                name=spec.display_name or "",
                description=spec.display_description or "",
                priceCents=price,
                stockCount=spec.stock_count,
                outOfStock=spec.out_of_stock,
                category=category_name,
                isSpecial=True,
            )
        )
    items.sort(key=lambda itm: (itm.category or "", itm.name))
    return CustomerMenuEnvelope(items=items)


class CustomerOrderItem(BaseModel):
    truckMenuItemId: int
    qty: int = Field(default=1, ge=1)
    modifiers: List[str] = []


class CustomerOrderPayload(BaseModel):
    shiftId: int
    items: List[CustomerOrderItem]
    customerPhone: Optional[str] = None
    customerName: Optional[str] = None
    loyaltyId: Optional[str] = None


class CustomerOrderResponse(BaseModel):
    orderId: int
    state: str


@router.post("/order", response_model=CustomerOrderResponse)
def create_customer_order(payload: CustomerOrderPayload, session: Session = Depends(get_session)):
    shift = session.get(TruckShift, payload.shiftId)
    if not shift:
        raise HTTPException(404, "Shift not found")
    if not payload.items:
        raise HTTPException(400, "No items supplied")
    subtotal = 0
    order_items: List[OrderItem] = []
    for item in payload.items:
        tmi = session.get(TruckMenuItem, item.truckMenuItemId)
        if not tmi or tmi.shift_id != payload.shiftId:
            raise HTTPException(400, "Invalid menu item")
        if not tmi.visible:
            raise HTTPException(400, "Item not available")
        base = session.get(MenuItem, tmi.menu_item_id) if tmi.menu_item_id else None
        price = tmi.price_override_cents
        if price is None and base:
            price = base.base_price_cents
        if price is None:
            raise HTTPException(400, "Menu item missing price")
        subtotal += price * item.qty
        order_items.append(
            OrderItem(
                menu_item_id=tmi.menu_item_id,
                truck_menu_item_id=tmi.id,
                name=tmi.display_name or (base.name if base else "Special"),
                qty=item.qty,
                price_cents=price,
                modifiers_json=json.dumps(item.modifiers),
            )
        )
    order = Order(
        shift_id=payload.shiftId,
        state=OrderState.NEW,
        subtotal_cents=subtotal,
        total_cents=subtotal,
        customer_phone=payload.customerPhone,
        customer_name=payload.customerName,
        loyalty_id=payload.loyaltyId,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    for oi in order_items:
        oi.order_id = order.id
        session.add(oi)
    session.commit()
    fire_and_forget(hub.emit(order.shift_id, {"event": "new_customer_order", "order_id": order.id}))
    return CustomerOrderResponse(orderId=order.id, state=order.state)


class PaymentWebhookPayload(BaseModel):
    orderId: int
    status: str
    transactionId: str


@router.post("/payment/webhook")
def payment_webhook(payload: PaymentWebhookPayload, session: Session = Depends(get_session)):
    order = session.get(Order, payload.orderId)
    if not order:
        raise HTTPException(404, "Order not found")
    if payload.status.lower() != "paid":
        return {"ignored": True}
    if order.state not in {OrderState.NEW, OrderState.PAID}:
        return {"state": order.state}
    order.state = OrderState.PAID
    order.payment_reference = payload.transactionId
    order.last_state_change_at = datetime.now(timezone.utc)
    items = session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    for item in items:
        tmi = None
        if item.truck_menu_item_id:
            tmi = session.get(TruckMenuItem, item.truck_menu_item_id)
        elif item.menu_item_id:
            tmi = session.exec(
                select(TruckMenuItem).where(
                    TruckMenuItem.shift_id == order.shift_id,
                    TruckMenuItem.menu_item_id == item.menu_item_id,
                )
            ).first()
        if tmi and tmi.stock_count is not None:
            if tmi.stock_count < item.qty:
                raise HTTPException(409, "Insufficient stock for item")
            tmi.stock_count -= item.qty
            tmi.last_stock_update_at = datetime.now(timezone.utc)
            session.add(
                InventoryAdjustment(
                    shift_id=order.shift_id,
                    truck_menu_item_id=tmi.id,
                    menu_item_id=tmi.menu_item_id,
                    delta=-item.qty,
                    reason="payment_notification",
                )
            )
            if tmi.stock_count == 0:
                tmi.out_of_stock = True
            session.add(tmi)
    session.add(order)
    session.commit()
    shift = session.get(TruckShift, order.shift_id)
    if shift:
        notification_service.notify_new_order(session, shift=shift, order_id=order.id)
    points_base = order.total_cents or 0
    if points_base <= 0:
        points_base = sum(item.price_cents * item.qty for item in items)
        if points_base:
            order.total_cents = points_base
            session.add(order)
            session.commit()
    points = 0
    if points_base > 0:
        points = max(1, points_base // 1000)
    if order.customer_phone and points:
        session.add(
            LoyaltyLedger(
                customer_phone=order.customer_phone,
                points=points,
                order_id=order.id,
                note="purchase",
            )
        )
        order.loyalty_points_awarded = points
        session.add(order)
        session.commit()
    fire_and_forget(hub.emit(order.shift_id, {"event": "payment_received", "order_id": order.id}))
    return {"state": order.state}


class ReconcilePayload(BaseModel):
    shiftId: int


@router.post("/reconcile")
def auto_reconcile(payload: ReconcilePayload, session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    orders = session.exec(
        select(Order).where(
            Order.shift_id == payload.shiftId,
            Order.state == OrderState.PAID,
        )
    ).all()
    for order in orders:
        order.state = OrderState.IN_QUEUE
        order.auto_reconciled_at = now
        order.last_state_change_at = now
        session.add(order)
    session.commit()
    return {"reconciled": len(orders)}


@router.get("/loyalty/{phone}")
def loyalty_balance(
    phone: str,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    entries = session.exec(
        select(LoyaltyLedger).where(LoyaltyLedger.customer_phone == phone)
    ).all()
    total = sum(entry.points for entry in entries)
    history = [
        {
            "points": entry.points,
            "orderId": entry.order_id,
            "note": entry.note,
            "createdAt": entry.created_at,
        }
        for entry in entries
    ]
    return {"phone": phone, "points": total, "history": history}
