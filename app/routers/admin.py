from __future__ import annotations

import json
from datetime import time as time_obj
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, delete, select

from ..auth import require_roles
from ..db import get_session
from ..models import (
    AuditLog,
    Location,
    OperatingHour,
    Staff,
    StaffRole,
    Truck,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])


class TruckOut(BaseModel):
    id: int
    name: str
    capacity: int
    tz: str
    active: bool
    operational_notes: str


class TruckCreate(BaseModel):
    name: str
    capacity: int = Field(default=12, ge=1)
    tz: str = "America/Moncton"
    active: bool = True
    operational_notes: str = ""


class TruckUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=1)
    tz: Optional[str] = None
    active: Optional[bool] = None
    operational_notes: Optional[str] = None


@router.get("/trucks", response_model=List[TruckOut])
def list_trucks(
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    trucks = session.exec(select(Truck).order_by(Truck.name.asc())).all()
    return [TruckOut(**t.model_dump(exclude_unset=False)) for t in trucks]


@router.post("/trucks", response_model=TruckOut)
def create_truck(
    payload: TruckCreate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    truck = Truck(**payload.model_dump())
    session.add(truck)
    session.commit()
    session.refresh(truck)
    session.add(
        AuditLog(
            staff_id=staff.id,
            action="create",
            entity_type="Truck",
            entity_id=truck.id,
            metadata_json=json.dumps(payload.model_dump()),
        )
    )
    session.commit()
    return TruckOut(**truck.model_dump(exclude_unset=False))


@router.patch("/trucks/{truck_id}", response_model=TruckOut)
def update_truck(
    truck_id: int,
    payload: TruckUpdate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    truck = session.get(Truck, truck_id)
    if not truck:
        raise HTTPException(404, "Truck not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(truck, key, value)
    session.add(truck)
    session.commit()
    session.add(
        AuditLog(
            staff_id=staff.id,
            action="update",
            entity_type="Truck",
            entity_id=truck.id,
            metadata_json=json.dumps(data),
        )
    )
    session.commit()
    return TruckOut(**truck.model_dump(exclude_unset=False))


@router.delete("/trucks/{truck_id}", status_code=204)
def delete_truck(
    truck_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    truck = session.get(Truck, truck_id)
    if not truck:
        raise HTTPException(404, "Truck not found")
    session.delete(truck)
    session.commit()
    session.add(
        AuditLog(
            staff_id=staff.id,
            action="delete",
            entity_type="Truck",
            entity_id=truck_id,
            metadata_json="{}",
        )
    )
    session.commit()
    return None


class LocationOut(BaseModel):
    id: int
    name: str
    address: str
    lat: float
    lon: float
    tax_region: str
    geofence_m: int


class LocationCreate(BaseModel):
    name: str
    address: str
    lat: float
    lon: float
    tax_region: str = "NB"
    geofence_m: int = Field(default=300, ge=0)


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    tax_region: Optional[str] = None
    geofence_m: Optional[int] = Field(default=None, ge=0)


@router.get("/locations", response_model=List[LocationOut])
def list_locations(
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    locations = session.exec(select(Location).order_by(Location.name.asc())).all()
    return [LocationOut(**loc.model_dump(exclude_unset=False)) for loc in locations]


@router.post("/locations", response_model=LocationOut)
def create_location(
    payload: LocationCreate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    loc = Location(**payload.model_dump())
    session.add(loc)
    session.commit()
    session.refresh(loc)
    session.add(
        AuditLog(
            staff_id=staff.id,
            action="create",
            entity_type="Location",
            entity_id=loc.id,
            metadata_json=json.dumps(payload.model_dump()),
        )
    )
    session.commit()
    return LocationOut(**loc.model_dump(exclude_unset=False))


@router.patch("/locations/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int,
    payload: LocationUpdate,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    loc = session.get(Location, location_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(loc, key, value)
    session.add(loc)
    session.commit()
    session.add(
        AuditLog(
            staff_id=staff.id,
            action="update",
            entity_type="Location",
            entity_id=loc.id,
            metadata_json=json.dumps(data),
        )
    )
    session.commit()
    return LocationOut(**loc.model_dump(exclude_unset=False))


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(
    location_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    loc = session.get(Location, location_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    session.delete(loc)
    session.commit()
    session.add(
        AuditLog(
            staff_id=staff.id,
            action="delete",
            entity_type="Location",
            entity_id=location_id,
            metadata_json="{}",
        )
    )
    session.commit()
    return None


class AssignmentPayload(BaseModel):
    truck_id: Optional[int] = None


@router.post("/staff/{staff_id}/assign", response_model=Optional[TruckOut])
def assign_staff(
    staff_id: int,
    payload: AssignmentPayload,
    actor: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    st = session.get(Staff, staff_id)
    if not st:
        raise HTTPException(404, "Staff not found")
    if payload.truck_id and not session.get(Truck, payload.truck_id):
        raise HTTPException(404, "Truck not found")
    st.truck_id = payload.truck_id
    session.add(st)
    session.commit()
    session.add(
        AuditLog(
            staff_id=actor.id,
            action="assign",
            entity_type="Staff",
            entity_id=st.id,
            metadata_json=json.dumps({"truck_id": payload.truck_id}),
        )
    )
    session.commit()
    truck = session.get(Truck, payload.truck_id) if payload.truck_id else None
    return TruckOut(**truck.model_dump(exclude_unset=False)) if truck else None


class OperatingHourOut(BaseModel):
    id: int
    day_of_week: int
    opens_at: str
    closes_at: str


class OperatingHourPayload(BaseModel):
    hours: List[OperatingHourOut]


@router.get("/trucks/{truck_id}/hours", response_model=OperatingHourPayload)
def get_hours(
    truck_id: int,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    truck = session.get(Truck, truck_id)
    if not truck:
        raise HTTPException(404, "Truck not found")
    hours = session.exec(
        select(OperatingHour)
        .where(OperatingHour.truck_id == truck_id)
        .order_by(OperatingHour.day_of_week.asc())
    ).all()
    return OperatingHourPayload(
        hours=[
            OperatingHourOut(
                id=hr.id,
                day_of_week=hr.day_of_week,
                opens_at=hr.opens_at.isoformat(),
                closes_at=hr.closes_at.isoformat(),
            )
            for hr in hours
        ]
    )


@router.put("/trucks/{truck_id}/hours", response_model=OperatingHourPayload)
def upsert_hours(
    truck_id: int,
    payload: OperatingHourPayload,
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    truck = session.get(Truck, truck_id)
    if not truck:
        raise HTTPException(404, "Truck not found")
    session.exec(delete(OperatingHour).where(OperatingHour.truck_id == truck_id))
    for hour in payload.hours:
        opens = time_obj.fromisoformat(hour.opens_at)
        closes = time_obj.fromisoformat(hour.closes_at)
        session.add(
            OperatingHour(
                truck_id=truck_id,
                day_of_week=hour.day_of_week,
                opens_at=opens,
                closes_at=closes,
            )
        )
    session.commit()
    session.add(
        AuditLog(
            staff_id=staff.id,
            action="update",
            entity_type="OperatingHour",
            entity_id=truck_id,
            metadata_json=json.dumps(
                {"hours": [hour.model_dump(exclude_unset=False) for hour in payload.hours]}
            ),
        )
    )
    session.commit()
    return get_hours(truck_id, staff, session)


class AuditLogOut(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: Optional[int]
    metadata: dict


@router.get("/audit-logs", response_model=List[AuditLogOut])
def list_audit_logs(
    staff: Staff = Depends(require_roles(StaffRole.MANAGER, StaffRole.OWNER)),
    session: Session = Depends(get_session),
):
    logs = session.exec(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)
    ).all()
    out: List[AuditLogOut] = []
    for log in logs:
        metadata = {}
        try:
            metadata = json.loads(log.metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {"raw": log.metadata_json}
        out.append(
            AuditLogOut(
                id=log.id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                metadata=metadata,
            )
        )
    return out
