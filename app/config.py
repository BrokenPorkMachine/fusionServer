import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("FX_DB_URL", "sqlite:///fusionx.db")
SECRET = os.getenv("FX_SECRET", "change-me")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("FX_ALLOWED_ORIGINS","*").split(",")]
TZ = os.getenv("FX_TZ", "America/Moncton")
