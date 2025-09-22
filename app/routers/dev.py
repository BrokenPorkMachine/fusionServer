from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from ..db import get_session
from ..models import *
from ..seed import seed
from ..hub import hub
import asyncio, json

router = APIRouter(prefix="/dev", tags=["dev"])

@router.post("/seed", status_code=204)
def dev_seed(session: Session = Depends(get_session)):
    seed(session)
    return JSONResponse(status_code=204, content=None)

@router.post("/sim-order/{shift_id}", status_code=201)
def dev_sim_order(shift_id: int, session: Session = Depends(get_session)):
    mi = session.exec(select(MenuItem)).all()
    if not mi:
        raise HTTPException(400, "seed menu first")
    order = Order(shift_id=shift_id, state=OrderState.PAID, subtotal_cents=1999, total_cents=2269, tax_cents=170)
    session.add(order); session.commit(); session.refresh(order)
    for m in mi[:2]:
        session.add(OrderItem(order_id=order.id, menu_item_id=m.id, name=m.name, qty=1, price_cents=m.base_price_cents))
    session.commit()
    asyncio.create_task(hub.emit(shift_id, {"event": "new_order", "order_id": order.id}))
    return {"order_id": order.id}
