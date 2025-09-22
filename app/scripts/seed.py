from sqlmodel import SQLModel
from app.db import engine
from app.seed import seed
from sqlmodel import Session

def main():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed(s)
    print("Seeded. (username=chef password=password)")

if __name__ == "__main__":
    main()
