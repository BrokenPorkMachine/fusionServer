from sqlmodel import create_engine, Session
from .config import DB_URL

engine = create_engine(DB_URL, echo=False)

def get_session():
    with Session(engine) as s:
        yield s
