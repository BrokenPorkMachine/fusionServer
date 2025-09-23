from sqlmodel import Session, select
from .models import *
from .auth import hash_pw

def seed(session: Session):
    t1 = session.exec(select(Truck).where(Truck.name == "Truck 1")).first()
    if not t1:
        t1 = Truck(name="Truck 1", capacity=12); session.add(t1); session.commit()

    chef = session.exec(select(Staff).where(Staff.username == "chef")).first()
    if not chef:
        chef = Staff(name="Chef", username="chef", password_hash=hash_pw("password"), role=StaffRole.TRUCK_LEAD, truck_id=t1.id)
        session.add(chef); session.commit()

    if session.exec(select(Location)).first() is None:
        session.add_all([
            Location(name="Downtown Lot", address="123 Main St, Moncton", lat=46.088, lon=-64.778, tax_region="NB"),
            Location(name="Riverfront Park", address="999 Riverfront, Moncton", lat=46.090, lon=-64.780, tax_region="NB"),
        ]); session.commit()

    categories = {c.name: c for c in session.exec(select(MenuCategory)).all()}
    if not categories:
        mains = MenuCategory(name="Mains", sort_order=0)
        snacks = MenuCategory(name="Snacks", sort_order=1)
        sweets = MenuCategory(name="Desserts", sort_order=2)
        session.add_all([mains, snacks, sweets])
        session.commit()
        categories = {c.name: c for c in session.exec(select(MenuCategory)).all()}

    if session.exec(select(MenuItem)).first() is None:
        session.add_all([
            MenuItem(
                name="General Tso's Chicken Poutine",
                base_price_cents=1499,
                description="crispy chicken + tso sauce",
                category_id=categories.get("Mains").id if categories.get("Mains") else None,
            ),
            MenuItem(
                name="Donair Poutine",
                base_price_cents=1499,
                description="donair meat + sweet sauce",
                category_id=categories.get("Mains").id if categories.get("Mains") else None,
            ),
            MenuItem(
                name="Crab Rangoon",
                base_price_cents=899,
                description="fried wontons",
                category_id=categories.get("Snacks").id if categories.get("Snacks") else None,
            ),
            MenuItem(
                name="Deep-Fried Cheesecake",
                base_price_cents=899,
                description="decadent dessert",
                category_id=categories.get("Desserts").id if categories.get("Desserts") else None,
            ),
        ])
        session.commit()
