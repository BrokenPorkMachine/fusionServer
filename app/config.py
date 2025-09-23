import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("FX_DB_URL", "sqlite:///fusionx.db")
SECRET = os.getenv("FX_SECRET", "change-me")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("FX_ALLOWED_ORIGINS","*").split(",")]
TZ = os.getenv("FX_TZ", "America/Moncton")
PUSH_NOTIFICATIONS_ENABLED = os.getenv("FX_PUSH_NOTIFICATIONS", "true").lower() == "true"
SMS_NOTIFICATIONS_ENABLED = os.getenv("FX_SMS_NOTIFICATIONS", "true").lower() == "true"
