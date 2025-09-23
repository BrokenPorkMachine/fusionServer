from typing import Optional
from datetime import datetime, time, timezone
from sqlmodel import SQLModel, Field


class StaffRole(str):
    OWNER = "Owner"
    MANAGER = "Manager"
    TRUCK_LEAD = "TruckLead"
    COOK = "Cook"
    CASHIER = "Cashier"


class NotificationChannel(str):
    PUSH = "push"
    SMS = "sms"
    EMAIL = "email"


class Staff(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    username: str
    password_hash: str
    role: str = StaffRole.TRUCK_LEAD
    truck_id: Optional[int] = Field(default=None, foreign_key="truck.id")
    phone_number: Optional[str] = None
    preferred_notification_channel: str = NotificationChannel.PUSH
    email: Optional[str] = None


class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id")
    apns_token: str
    platform: str = "ios"
    app_version: str = "0"
    os_version: str = "unknown"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class Truck(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    capacity: int = 12
    tz: str = "America/Moncton"
    active: bool = True
    operational_notes: str = ""


class OperatingHour(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    truck_id: int = Field(foreign_key="truck.id")
    day_of_week: int
    opens_at: time
    closes_at: time


class Location(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    address: str
    lat: float
    lon: float
    tax_region: str = "NB"
    geofence_m: int = 300


class ShiftStatus(str):
    CHECKED_IN = "CHECKED_IN"
    PAUSED = "PAUSED"
    CHECKED_OUT = "CHECKED_OUT"


class TruckShift(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    truck_id: int = Field(foreign_key="truck.id")
    location_id: int = Field(foreign_key="location.id")
    status: str = Field(default=ShiftStatus.CHECKED_IN)
    starts_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ends_at: Optional[datetime] = None
    resume_at: Optional[datetime] = None
    throttle_per_5m: int = 12
    slot_capacity_per_min: int = 6
    notes: str = ""
    lat: float = 0.0
    lon: float = 0.0


class MenuCategory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sort_order: int = 0


class MenuItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    base_price_cents: int
    category_id: Optional[int] = Field(default=None, foreign_key="menucategory.id")
    sort_order: int = 0
    is_active: bool = True
    available_start: Optional[datetime] = None
    available_end: Optional[datetime] = None


class TruckMenuItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(foreign_key="truckshift.id")
    menu_item_id: Optional[int] = Field(default=None, foreign_key="menuitem.id")
    visible: bool = True
    price_override_cents: Optional[int] = None
    stock_count: Optional[int] = None
    out_of_stock: bool = False
    low_stock_threshold: int = 2
    prep_time_sec: int = 300
    display_name: Optional[str] = None
    display_description: Optional[str] = None
    category_id: Optional[int] = Field(default=None, foreign_key="menucategory.id")
    is_special: bool = False
    available_start: Optional[datetime] = None
    available_end: Optional[datetime] = None
    display_order: int = 0
    last_stock_update_at: Optional[datetime] = None


class OrderState(str):
    NEW = "NEW"
    PAID = "PAID"
    IN_QUEUE = "IN_QUEUE"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    ON_HOLD = "ON_HOLD"
    PICKED_UP = "PICKED_UP"
    CANCELED = "CANCELED"
    REFUNDED = "REFUNDED"


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(foreign_key="truckshift.id")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    loyalty_id: Optional[str] = None
    state: str = Field(default=OrderState.PAID)
    previous_state: Optional[str] = None
    pickup_eta: Optional[datetime] = None
    subtotal_cents: int = 0
    tax_cents: int = 0
    tip_cents: int = 0
    total_cents: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prep_completed_at: Optional[datetime] = None
    on_hold_until: Optional[datetime] = None
    hold_reason: Optional[str] = None
    cancellation_reason: Optional[str] = None
    canceled_at: Optional[datetime] = None
    refund_reason: Optional[str] = None
    refunded_at: Optional[datetime] = None
    payment_reference: Optional[str] = None
    last_state_change_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    loyalty_points_awarded: int = 0
    auto_reconciled_at: Optional[datetime] = None


class OrderItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    menu_item_id: Optional[int] = Field(default=None, foreign_key="menuitem.id")
    truck_menu_item_id: Optional[int] = Field(default=None, foreign_key="truckmenuitem.id")
    name: str
    qty: int = 1
    price_cents: int = 0
    modifiers_json: str = "[]"


class InventoryAdjustment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(foreign_key="truckshift.id")
    truck_menu_item_id: Optional[int] = Field(default=None, foreign_key="truckmenuitem.id")
    menu_item_id: Optional[int] = Field(default=None, foreign_key="menuitem.id")
    delta: int
    reason: str
    staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    metadata_json: str = "{}"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: Optional[int] = Field(default=None)
    staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    channel: str
    payload: str
    status: str = "queued"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LoyaltyLedger(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_phone: str
    points: int
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeeklySummaryDigest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: str
    delivered: bool = False
