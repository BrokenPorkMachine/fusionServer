from __future__ import annotations

from sqlmodel import Session, select

from ..config import PUSH_NOTIFICATIONS_ENABLED, SMS_NOTIFICATIONS_ENABLED
from ..models import (
    Device,
    NotificationChannel,
    NotificationLog,
    Staff,
    TruckShift,
)


class NotificationService:
    """Queues push and SMS notifications for staff devices."""

    def queue_push(self, session: Session, *, shift_id: int, staff: Staff, message: str) -> None:
        if not PUSH_NOTIFICATIONS_ENABLED:
            return
        devices = session.exec(
            select(Device).where(Device.staff_id == staff.id, Device.revoked_at.is_(None))
        ).all()
        payload = {
            "message": message,
            "staff_id": staff.id,
            "shift_id": shift_id,
        }
        for device in devices:
            session.add(
                NotificationLog(
                    shift_id=shift_id,
                    staff_id=staff.id,
                    device_id=device.id,
                    channel=NotificationChannel.PUSH,
                    payload=str(payload),
                    status="queued",
                )
            )

    def queue_sms(self, session: Session, *, shift_id: int, staff: Staff, message: str) -> None:
        if not SMS_NOTIFICATIONS_ENABLED:
            return
        payload = {
            "message": message,
            "staff_id": staff.id,
            "phone": staff.phone_number,
            "shift_id": shift_id,
        }
        session.add(
            NotificationLog(
                shift_id=shift_id,
                staff_id=staff.id,
                channel=NotificationChannel.SMS,
                payload=str(payload),
                status="queued" if staff.phone_number else "skipped",
            )
        )

    def notify_staff(self, session: Session, *, shift: TruckShift, message: str) -> None:
        staff_members = session.exec(
            select(Staff).where(Staff.truck_id == shift.truck_id)
        ).all()
        for member in staff_members:
            if member.preferred_notification_channel == NotificationChannel.SMS:
                self.queue_sms(session, shift_id=shift.id, staff=member, message=message)
            else:
                self.queue_push(session, shift_id=shift.id, staff=member, message=message)
        session.commit()

    def notify_low_stock(self, session: Session, *, shift: TruckShift, menu_item_name: str) -> None:
        message = f"Low stock: {menu_item_name}"
        self.notify_staff(session, shift=shift, message=message)

    def notify_new_order(self, session: Session, *, shift: TruckShift, order_id: int) -> None:
        message = f"New order {order_id} ready for action"
        self.notify_staff(session, shift=shift, message=message)


notification_service = NotificationService()
