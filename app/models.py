from typing import Optional, List
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field

class StaffRole(str):
    OWNER = "Owner"
    MANAGER = "Manager"
    TRUCK_LEAD = "TruckLead"
    COOK = "Cook"
    CASHIER = "Cashier"

class Staff(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    username: str
    password_hash: str
    role: str = StaffRole.TRUCK_LEAD
    truck_id: Optional[int] = Field(default=None, foreign_key="truck.id")

class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id")
    apns_token: str
    platform: str = "ios"
    app_version: str = "0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Truck(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    capacity: int = 12
    tz: str = "America/Moncton"
    active: bool = True

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

class MenuItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    base_price_cents: int

class TruckMenuItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(foreign_key="truckshift.id")
    menu_item_id: int = Field(foreign_key="menuitem.id")
    visible: bool = True
    price_override_cents: Optional[int] = None
    stock_count: Optional[int] = None
    out_of_stock: bool = False
    low_stock_threshold: int = 2
    prep_time_sec: int = 300

class OrderState(str):
    NEW = "NEW"
    PAID = "PAID"
    IN_QUEUE = "IN_QUEUE"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    PICKED_UP = "PICKED_UP"
    CANCELED = "CANCELED"
    REFUNDED = "REFUNDED"

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(foreign_key="truckshift.id")
    customer_phone: Optional[str] = None
    state: str = Field(default=OrderState.PAID)
    pickup_eta: Optional[datetime] = None
    subtotal_cents: int = 0
    tax_cents: int = 0
    tip_cents: int = 0
    total_cents: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    menu_item_id: int = Field(foreign_key="menuitem.id")
    name: str
    qty: int = 1
    price_cents: int = 0
    modifiers_json: str = "[]"
