import hashlib
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select
from .config import SECRET
from .db import get_session
from .models import Staff

signer = URLSafeTimedSerializer(SECRET)
TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

def hash_pw(pw: str) -> str:
    import hashlib
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def make_token(staff: Staff) -> str:
    return signer.dumps({"sid": staff.id, "role": staff.role})

def verify_token(token: str) -> dict:
    try:
        return signer.loads(token, max_age=TOKEN_MAX_AGE)
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Token expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_auth(authorization: str | None = Header(default=None), session: Session = Depends(get_session)) -> Staff:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    st = session.get(Staff, payload["sid"])
    if not st:
        raise HTTPException(status_code=401, detail="Unknown user")
    return st
