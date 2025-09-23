from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import require_roles
from ..db import get_session
from ..models import (
    AuditLog,
    InventoryAdjustment,
    MenuCategory,
    MenuItem,
    Staff,
    StaffRole,
    TruckMenuItem,
    TruckShift,
)


router = APIRouter(prefix="/api/menu", tags=["menu"])


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


class CategoryOut(BaseModel):
    id: int
    name: str
    sort_order: int


class CategoryCreate(BaseModel):
    name: str
    sort_order: int = Field(default=0, ge=0)


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = Field(default=None, ge=0)


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    cats = session.exec(select(MenuCategory).order_by(MenuCategory.sort_order.asc())).all()
    return [CategoryOut(id=c.id, name=c.name, sort_order=c.sort_order) for c in cats]


@router.post("/categories", response_model=CategoryOut)
def create_category(
    payload: CategoryCreate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    cat = MenuCategory(**payload.model_dump())
    session.add(cat)
    session.commit()
    session.refresh(cat)
    _record_audit(session, staff, "create", "MenuCategory", cat.id, cat.model_dump())
    session.commit()
    return CategoryOut(id=cat.id, name=cat.name, sort_order=cat.sort_order)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    cat = session.get(MenuCategory, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    if payload.name is not None:
        cat.name = payload.name
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    session.add(cat)
    session.commit()
    _record_audit(
        session,
        staff,
        "update",
        "MenuCategory",
        cat.id,
        {"name": cat.name, "sort_order": cat.sort_order},
    )
    session.commit()
    return CategoryOut(id=cat.id, name=cat.name, sort_order=cat.sort_order)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    cat = session.get(MenuCategory, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    session.delete(cat)
    session.commit()
    _record_audit(session, staff, "delete", "MenuCategory", category_id, None)
    session.commit()
    return None


class MenuItemOut(BaseModel):
    id: int
    name: str
    description: str
    base_price_cents: int
    category_id: Optional[int]
    sort_order: int
    is_active: bool
    available_start: Optional[datetime]
    available_end: Optional[datetime]


class MenuItemCreate(BaseModel):
    name: str
    description: str = ""
    base_price_cents: int = Field(ge=0)
    category_id: Optional[int] = None
    sort_order: int = Field(default=0, ge=0)
    available_start: Optional[datetime] = None
    available_end: Optional[datetime] = None
    is_active: bool = True


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_price_cents: Optional[int] = Field(default=None, ge=0)
    category_id: Optional[int] = None
    sort_order: Optional[int] = Field(default=None, ge=0)
    available_start: Optional[datetime] = None
    available_end: Optional[datetime] = None
    is_active: Optional[bool] = None


@router.get("/items", response_model=List[MenuItemOut])
def list_menu_items(
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    items = session.exec(select(MenuItem).order_by(MenuItem.sort_order.asc())).all()
    return [MenuItemOut(**item.model_dump(exclude_unset=False)) for item in items]


@router.post("/items", response_model=MenuItemOut)
def create_menu_item(
    payload: MenuItemCreate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    if payload.category_id:
        if not session.get(MenuCategory, payload.category_id):
            raise HTTPException(404, "Category not found")
    item = MenuItem(**payload.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    item_data = item.model_dump(exclude_unset=False)
    _record_audit(session, staff, "create", "MenuItem", item.id, item_data)
    session.commit()
    return MenuItemOut(**item_data)


@router.patch("/items/{item_id}", response_model=MenuItemOut)
def update_menu_item(
    item_id: int,
    payload: MenuItemUpdate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    item = session.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data and data["category_id"]:
        if not session.get(MenuCategory, data["category_id"]):
            raise HTTPException(404, "Category not found")
    for key, value in data.items():
        setattr(item, key, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    item_data = item.model_dump(exclude_unset=False)
    _record_audit(session, staff, "update", "MenuItem", item.id, data)
    session.commit()
    return MenuItemOut(**item_data)


@router.delete("/items/{item_id}", status_code=204)
def delete_menu_item(
    item_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    item = session.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    session.delete(item)
    session.commit()
    _record_audit(session, staff, "delete", "MenuItem", item_id, None)
    session.commit()
    return None


class SpecialCreate(BaseModel):
    name: str
    description: str = ""
    price_cents: int = Field(ge=0)
    category_id: Optional[int] = None
    available_start: Optional[datetime] = None
    available_end: Optional[datetime] = None
    stock_count: Optional[int] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = Field(default=2, ge=0)
    display_order: int = Field(default=0, ge=0)


class SpecialOut(BaseModel):
    id: int
    name: str
    description: str
    price_cents: int
    available_start: Optional[datetime]
    available_end: Optional[datetime]
    stock_count: Optional[int]
    out_of_stock: bool
    display_order: int


class SpecialUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_cents: Optional[int] = Field(default=None, ge=0)
    available_start: Optional[datetime] = None
    available_end: Optional[datetime] = None
    stock_count: Optional[int] = Field(default=None, ge=0)
    out_of_stock: Optional[bool] = None
    display_order: Optional[int] = Field(default=None, ge=0)


@router.get("/shift/{shift_id}/specials", response_model=List[SpecialOut])
def list_specials(
    shift_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER, StaffRole.TRUCK_LEAD)),
    session: Session = Depends(get_session),
):
    shift = session.get(TruckShift, shift_id)
    if not shift:
        raise HTTPException(404, "Shift not found")
    specials = session.exec(
        select(TruckMenuItem)
        .where(TruckMenuItem.shift_id == shift_id, TruckMenuItem.is_special == True)
        .order_by(TruckMenuItem.display_order.asc())
    ).all()
    return [
        SpecialOut(
            id=spec.id,
            name=spec.display_name or "",
            description=spec.display_description or "",
            price_cents=spec.price_override_cents or 0,
            available_start=spec.available_start,
            available_end=spec.available_end,
            stock_count=spec.stock_count,
            out_of_stock=spec.out_of_stock,
            display_order=spec.display_order,
        )
        for spec in specials
    ]


@router.post("/shift/{shift_id}/specials", response_model=SpecialOut)
def create_special(
    shift_id: int,
    payload: SpecialCreate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER, StaffRole.TRUCK_LEAD)),
    session: Session = Depends(get_session),
):
    shift = session.get(TruckShift, shift_id)
    if not shift:
        raise HTTPException(404, "Shift not found")
    spec = TruckMenuItem(
        shift_id=shift_id,
        display_name=payload.name,
        display_description=payload.description,
        price_override_cents=payload.price_cents,
        category_id=payload.category_id,
        is_special=True,
        available_start=payload.available_start,
        available_end=payload.available_end,
        stock_count=payload.stock_count,
        low_stock_threshold=payload.low_stock_threshold or 0,
        display_order=payload.display_order,
    )
    session.add(spec)
    session.commit()
    session.refresh(spec)
    _record_audit(
        session,
        staff,
        "create",
        "ShiftSpecial",
        spec.id,
        payload.model_dump(),
    )
    session.commit()
    return SpecialOut(
        id=spec.id,
        name=spec.display_name or "",
        description=spec.display_description or "",
        price_cents=spec.price_override_cents or 0,
        available_start=spec.available_start,
        available_end=spec.available_end,
        stock_count=spec.stock_count,
        out_of_stock=spec.out_of_stock,
        display_order=spec.display_order,
    )


@router.patch("/shift/{shift_id}/specials/{special_id}", response_model=SpecialOut)
def update_special(
    shift_id: int,
    special_id: int,
    payload: SpecialUpdate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER, StaffRole.TRUCK_LEAD)),
    session: Session = Depends(get_session),
):
    spec = session.get(TruckMenuItem, special_id)
    if not spec or spec.shift_id != shift_id or not spec.is_special:
        raise HTTPException(404, "Special not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        spec.display_name = data["name"]
    if "description" in data:
        spec.display_description = data["description"]
    if "price_cents" in data:
        spec.price_override_cents = data["price_cents"]
    if "available_start" in data:
        spec.available_start = data["available_start"]
    if "available_end" in data:
        spec.available_end = data["available_end"]
    if "stock_count" in data:
        previous = spec.stock_count or 0
        spec.stock_count = data["stock_count"]
        delta = (spec.stock_count or 0) - previous
        if delta != 0:
            session.add(
                InventoryAdjustment(
                    shift_id=shift_id,
                    truck_menu_item_id=spec.id,
                    delta=delta,
                    reason="special_update",
                    staff_id=staff.id,
                )
            )
    if "out_of_stock" in data and data["out_of_stock"] is not None:
        spec.out_of_stock = data["out_of_stock"]
    if "display_order" in data and data["display_order"] is not None:
        spec.display_order = data["display_order"]
    session.add(spec)
    session.commit()
    _record_audit(session, staff, "update", "ShiftSpecial", spec.id, data)
    session.commit()
    return SpecialOut(
        id=spec.id,
        name=spec.display_name or "",
        description=spec.display_description or "",
        price_cents=spec.price_override_cents or 0,
        available_start=spec.available_start,
        available_end=spec.available_end,
        stock_count=spec.stock_count,
        out_of_stock=spec.out_of_stock,
        display_order=spec.display_order,
    )


@router.delete("/shift/{shift_id}/specials/{special_id}", status_code=204)
def delete_special(
    shift_id: int,
    special_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER, StaffRole.TRUCK_LEAD)),
    session: Session = Depends(get_session),
):
    spec = session.get(TruckMenuItem, special_id)
    if not spec or spec.shift_id != shift_id or not spec.is_special:
        raise HTTPException(404, "Special not found")
    session.delete(spec)
    session.commit()
    _record_audit(session, staff, "delete", "ShiftSpecial", special_id, None)
    session.commit()
    return None
