from __future__ import annotations

import json
from typing import Tuple

from sqlmodel import Session, select

from app.auth import hash_pw
from app.models import (
    InventoryAdjustment,
    LoyaltyLedger,
    Order,
    OrderState,
    Staff,
    StaffRole,
    Truck,
    TruckMenuItem,
    TruckShift,
)


def login_token(client, username: str, password: str) -> str:
    resp = client.post("/api/mobile/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_manager(engine) -> Tuple[str, int]:
    with Session(engine) as session:
        truck = session.exec(select(Truck)).first()
        truck_id = truck.id
        manager = Staff(
            name="Manager",
            username="manager",
            password_hash=hash_pw("secret"),
            role=StaffRole.MANAGER,
            truck_id=truck_id,
        )
        session.add(manager)
        session.commit()
    return "manager", truck_id


def ensure_shift(client, engine, token: str) -> int:
    locations = client.get("/api/mobile/locations", headers=auth_headers(token)).json()[
        "locations"
    ]
    trucks = client.get("/api/mobile/trucks", headers=auth_headers(token)).json()[
        "trucks"
    ]
    resp = client.post(
        "/api/mobile/shift/checkin",
        headers=auth_headers(token),
        json={"truck_id": trucks[0]["id"], "location_id": locations[0]["id"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_menu_crud_and_specials(app_client):
    client, engine = app_client
    manager_username, _ = create_manager(engine)
    manager_token = login_token(client, manager_username, "secret")
    chef_token = login_token(client, "chef", "password")
    shift_id = ensure_shift(client, engine, chef_token)

    create_payload = {
        "name": "Tempura Shrimp",
        "description": "crispy",
        "base_price_cents": 1299,
        "sort_order": 3,
    }
    resp = client.post(
        "/api/menu/items",
        headers=auth_headers(manager_token),
        json=create_payload,
    )
    assert resp.status_code == 200, resp.text
    menu_item_id = resp.json()["id"]

    resp = client.patch(
        f"/api/menu/items/{menu_item_id}",
        headers=auth_headers(manager_token),
        json={"description": "crispy shrimp", "sort_order": 4},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "crispy shrimp"

    special_payload = {
        "name": "Lobster Roll",
        "description": "butter poached",
        "price_cents": 1899,
        "stock_count": 5,
    }
    resp = client.post(
        f"/api/menu/shift/{shift_id}/specials",
        headers=auth_headers(manager_token),
        json=special_payload,
    )
    assert resp.status_code == 200, resp.text

    menu_resp = client.get(
        f"/api/mobile/shift/{shift_id}/menu", headers=auth_headers(chef_token)
    )
    assert menu_resp.status_code == 200
    items = menu_resp.json()["items"]
    assert any(item.get("isSpecial") for item in items)


def test_payment_and_inventory_flow(app_client):
    client, engine = app_client
    chef_token = login_token(client, "chef", "password")
    shift_id = ensure_shift(client, engine, chef_token)

    menu_resp = client.get(
        f"/api/customer/menu/{shift_id}", headers=auth_headers(chef_token)
    )
    assert menu_resp.status_code == 200
    first_item = menu_resp.json()["items"][0]
    stock_payload = {
        "updates": [
            {
                "truckMenuItemId": first_item["truckMenuItemId"],
                "stockCount": 5,
            }
        ]
    }
    resp = client.patch(
        f"/api/mobile/shift/{shift_id}/inventory",
        headers=auth_headers(chef_token),
        json=stock_payload,
    )
    assert resp.status_code == 204

    order_payload = {
        "shiftId": shift_id,
        "items": [
            {
                "truckMenuItemId": first_item["truckMenuItemId"],
                "qty": 2,
                "modifiers": ["extra sauce"],
            }
        ],
        "customerPhone": "5550000",
        "customerName": "Guest",
    }
    order_resp = client.post("/api/customer/order", json=order_payload)
    assert order_resp.status_code == 200, order_resp.text
    order_id = order_resp.json()["orderId"]

    webhook_resp = client.post(
        "/api/customer/payment/webhook",
        json={
            "orderId": order_id,
            "status": "paid",
            "transactionId": "txn_123",
        },
    )
    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["state"] == OrderState.PAID

    detail = client.get(
        f"/api/mobile/order/{order_id}", headers=auth_headers(chef_token)
    ).json()
    assert detail["state"] == OrderState.PAID

    with Session(engine) as session:
        tmi = session.get(TruckMenuItem, first_item["truckMenuItemId"])
        assert tmi.stock_count == 3
        adjustments = session.exec(select(InventoryAdjustment)).all()
        assert any(adj.delta == -2 for adj in adjustments)
        ledger = session.exec(select(LoyaltyLedger)).all()
        assert ledger and ledger[0].points > 0


def test_order_hold_resume_cancel_and_bulk(app_client):
    client, engine = app_client
    chef_token = login_token(client, "chef", "password")
    shift_id = ensure_shift(client, engine, chef_token)
    order_id = client.post(
        f"/dev/sim-order/{shift_id}", headers=auth_headers(chef_token)
    ).json()["order_id"]

    resp = client.post(
        f"/api/mobile/order/{order_id}/advance",
        headers=auth_headers(chef_token),
        json={"to": OrderState.IN_PROGRESS},
    )
    assert resp.status_code == 200

    hold_resp = client.post(
        f"/api/mobile/order/{order_id}/hold",
        headers=auth_headers(chef_token),
        json={"minutes": 5, "reason": "Waiting"},
    )
    assert hold_resp.status_code == 200
    assert hold_resp.json()["state"] == OrderState.ON_HOLD

    resume_resp = client.post(
        f"/api/mobile/order/{order_id}/resume",
        headers=auth_headers(chef_token),
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["state"] in {
        OrderState.IN_PROGRESS,
        OrderState.IN_QUEUE,
    }

    ready_resp = client.post(
        f"/api/mobile/order/{order_id}/advance",
        headers=auth_headers(chef_token),
        json={"to": OrderState.READY},
    )
    assert ready_resp.status_code == 200

    bulk_resp = client.post(
        f"/api/mobile/shift/{shift_id}/advance-ready",
        headers=auth_headers(chef_token),
        json={"orderIds": [order_id]},
    )
    assert bulk_resp.status_code == 200
    assert bulk_resp.json()["updated"] == 1

    cancel_order = client.post(
        f"/dev/sim-order/{shift_id}", headers=auth_headers(chef_token)
    ).json()["order_id"]
    cancel_resp = client.post(
        f"/api/mobile/order/{cancel_order}/cancel",
        headers=auth_headers(chef_token),
        json={"reason": "Guest no-show", "refund": False},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["state"] == OrderState.CANCELED


def test_device_management_and_profile(app_client):
    client, engine = app_client
    chef_token = login_token(client, "chef", "password")
    register_resp = client.post(
        "/api/mobile/devices/register",
        headers=auth_headers(chef_token),
        json={
            "apns_token": "token-123",
            "platform": "ios",
            "app_version": "1.0",
            "os_version": "17.0",
        },
    )
    assert register_resp.status_code == 204

    heartbeat = client.post(
        "/api/mobile/devices/heartbeat",
        headers=auth_headers(chef_token),
        json={"apns_token": "token-123"},
    )
    assert heartbeat.status_code == 204

    devices = client.get(
        "/api/mobile/devices", headers=auth_headers(chef_token)
    ).json()
    assert len(devices) == 1
    device_id = devices[0]["id"]

    revoke = client.delete(
        f"/api/mobile/devices/{device_id}", headers=auth_headers(chef_token)
    )
    assert revoke.status_code == 204

    hb_fail = client.post(
        "/api/mobile/devices/heartbeat",
        headers=auth_headers(chef_token),
        json={"apns_token": "token-123"},
    )
    assert hb_fail.status_code == 403

    profile_resp = client.patch(
        "/api/mobile/staff/profile",
        headers=auth_headers(chef_token),
        json={
            "phoneNumber": "5065550101",
            "preferredChannel": "sms",
            "password": "newpass1",
        },
    )
    assert profile_resp.status_code == 200
    assert profile_resp.json()["phoneNumber"] == "5065550101"

    new_token = login_token(client, "chef", "newpass1")
    assert new_token


def test_admin_hours_and_weekly_summary(app_client):
    client, engine = app_client
    manager_username, truck_id = create_manager(engine)
    manager_token = login_token(client, manager_username, "secret")

    hours_payload = {
        "hours": [
            {"id": 0, "day_of_week": 0, "opens_at": "08:00:00", "closes_at": "17:00:00"}
        ]
    }
    resp = client.put(
        f"/api/admin/trucks/{truck_id}/hours",
        headers=auth_headers(manager_token),
        json=hours_payload,
    )
    assert resp.status_code == 200
    fetched = client.get(
        f"/api/admin/trucks/{truck_id}/hours",
        headers=auth_headers(manager_token),
    ).json()
    assert fetched["hours"][0]["opens_at"].startswith("08:00")

    summary_resp = client.post(
        "/api/analytics/weekly-summary",
        headers=auth_headers(manager_token),
    )
    assert summary_resp.status_code == 200
    assert "orderCount" in summary_resp.json()


def test_analytics_export_and_dashboard(app_client):
    client, engine = app_client
    chef_token = login_token(client, "chef", "password")
    shift_id = ensure_shift(client, engine, chef_token)
    client.post(
        f"/dev/sim-order/{shift_id}", headers=auth_headers(chef_token)
    )

    dashboard = client.get(
        f"/api/analytics/shift/{shift_id}/dashboard",
        headers=auth_headers(chef_token),
    )
    assert dashboard.status_code == 200
    assert "ordersByState" in dashboard.json()

    export_json = client.get(
        f"/api/analytics/shift/{shift_id}/export",
        headers=auth_headers(chef_token),
    )
    assert export_json.status_code == 200
    export_csv = client.get(
        f"/api/analytics/shift/{shift_id}/export?format=csv",
        headers=auth_headers(chef_token),
    )
    assert export_csv.status_code == 200


def test_customer_loyalty_lookup(app_client):
    client, engine = app_client
    chef_token = login_token(client, "chef", "password")
    shift_id = ensure_shift(client, engine, chef_token)
    menu_item = client.get(
        f"/api/customer/menu/{shift_id}", headers=auth_headers(chef_token)
    ).json()["items"][0]
    order = client.post(
        "/api/customer/order",
        json={
            "shiftId": shift_id,
            "items": [
                {"truckMenuItemId": menu_item["truckMenuItemId"], "qty": 1}
            ],
            "customerPhone": "555-1212",
        },
    ).json()
    client.post(
        "/api/customer/payment/webhook",
        json={"orderId": order["orderId"], "status": "paid", "transactionId": "abc"},
    )

    manager_username, _ = create_manager(engine)
    manager_token = login_token(client, manager_username, "secret")
    loyalty = client.get(
        "/api/customer/loyalty/555-1212",
        headers=auth_headers(manager_token),
    )
    assert loyalty.status_code == 200
    assert loyalty.json()["points"] >= 1


def test_health_endpoints(app_client):
    client, _ = app_client
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
