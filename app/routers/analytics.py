from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..auth import require_roles
from ..db import get_session
from ..models import (
    InventoryAdjustment,
    NotificationLog,
    Order,
    OrderItem,
    Staff,
    StaffRole,
    TruckMenuItem,
    TruckShift,
    WeeklySummaryDigest,
)


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _order_to_dict(order: Order, session: Session) -> Dict:
    items = session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    return {
        "id": order.id,
        "state": order.state,
        "totalCents": order.total_cents,
        "subtotalCents": order.subtotal_cents,
        "taxCents": order.tax_cents,
        "tipCents": order.tip_cents,
        "customerPhone": order.customer_phone,
        "createdAt": order.created_at,
        "prepCompletedAt": order.prep_completed_at,
        "items": [
            {
                "name": item.name,
                "qty": item.qty,
                "priceCents": item.price_cents,
                "modifiers": json.loads(item.modifiers_json or "[]"),
            }
            for item in items
        ],
    }


@router.get("/shift/{shift_id}/export")
def export_shift(
    shift_id: int,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER, StaffRole.TRUCK_LEAD)),
    session: Session = Depends(get_session),
):
    shift = session.get(TruckShift, shift_id)
    if not shift:
        raise HTTPException(404, "Shift not found")
    orders = session.exec(select(Order).where(Order.shift_id == shift_id)).all()
    adjustments = session.exec(
        select(InventoryAdjustment)
        .where(InventoryAdjustment.shift_id == shift_id)
        .order_by(InventoryAdjustment.created_at.asc())
    ).all()
    data = {
        "shift": {
            "id": shift.id,
            "truck_id": shift.truck_id,
            "location_id": shift.location_id,
            "started_at": shift.starts_at,
            "ended_at": shift.ends_at,
        },
        "orders": [_order_to_dict(order, session) for order in orders],
        "inventoryAdjustments": [
            {
                "id": adj.id,
                "menuItemId": adj.menu_item_id,
                "truckMenuItemId": adj.truck_menu_item_id,
                "delta": adj.delta,
                "reason": adj.reason,
                "createdAt": adj.created_at,
            }
            for adj in adjustments
        ],
    }
    if format == "json":
        return data
    output = io.StringIO()
    fieldnames = [
        "order_id",
        "state",
        "item_name",
        "qty",
        "price_cents",
        "customer_phone",
        "created_at",
        "prep_completed_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for order in data["orders"]:
        for item in order["items"]:
            writer.writerow(
                {
                    "order_id": order["id"],
                    "state": order["state"],
                    "item_name": item["name"],
                    "qty": item["qty"],
                    "price_cents": item["priceCents"],
                    "customer_phone": order["customerPhone"],
                    "created_at": order["createdAt"],
                    "prep_completed_at": order["prepCompletedAt"],
                }
            )
    output.seek(0)
    return StreamingResponse(
        output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=shift.csv"}
    )


@router.get("/shift/{shift_id}/dashboard")
def shift_dashboard(
    shift_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER, StaffRole.TRUCK_LEAD)),
    session: Session = Depends(get_session),
):
    shift = session.get(TruckShift, shift_id)
    if not shift:
        raise HTTPException(404, "Shift not found")
    orders = session.exec(select(Order).where(Order.shift_id == shift_id)).all()
    orders_by_state: Dict[str, int] = {}
    prep_times: List[float] = []
    last_hour = datetime.now(timezone.utc) - timedelta(hours=1)
    last_hour_count = 0
    def _ensure_aware(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    for order in orders:
        orders_by_state[order.state] = orders_by_state.get(order.state, 0) + 1
        created_at = _ensure_aware(order.created_at)
        completed_at = _ensure_aware(order.prep_completed_at)
        if completed_at and created_at:
            duration = (completed_at - created_at).total_seconds()
            if duration >= 0:
                prep_times.append(duration)
        if created_at and created_at >= last_hour:
            last_hour_count += 1
    avg_prep = int(sum(prep_times) / len(prep_times)) if prep_times else None
    tmis = session.exec(select(TruckMenuItem).where(TruckMenuItem.shift_id == shift_id)).all()
    low_stock = []
    for tmi in tmis:
        if tmi.out_of_stock:
            low_stock.append({"name": tmi.display_name or "", "menuItemId": tmi.menu_item_id})
        elif tmi.stock_count is not None and tmi.stock_count <= (tmi.low_stock_threshold or 0):
            low_stock.append({"name": tmi.display_name or "", "menuItemId": tmi.menu_item_id})
    return {
        "shiftId": shift.id,
        "ordersByState": orders_by_state,
        "averagePrepSeconds": avg_prep,
        "ordersLastHour": last_hour_count,
        "lowStockItems": low_stock,
    }


@router.post("/weekly-summary")
def weekly_summary(
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=7)
    orders = session.exec(select(Order).where(Order.created_at >= window_start)).all()
    revenue = sum(order.total_cents for order in orders)
    low_stock_alerts = session.exec(
        select(NotificationLog)
        .where(NotificationLog.created_at >= window_start)
        .where(NotificationLog.payload.contains("Low stock"))
    ).all()
    summary = {
        "generatedAt": now.isoformat(),
        "orderCount": len(orders),
        "revenueCents": revenue,
        "lowStockAlerts": len(low_stock_alerts),
    }
    session.add(WeeklySummaryDigest(payload=json.dumps(summary)))
    session.commit()
    return summary
