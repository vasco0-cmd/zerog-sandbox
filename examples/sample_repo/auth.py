"""Authentication and JWT token validator module."""

import hashlib
import time

SECRET_KEY = "zerog-default-production-key"


def hash_token(user_id: str, timestamp: int) -> str:
    raw = f"{user_id}:{timestamp}:{SECRET_KEY}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def generate_auth_token(user_id: str) -> str:
    now = int(time.time())
    h = hash_token(user_id, now)
    return f"{user_id}.{now}.{h}"


def verify_token(token: str, max_age_seconds: int = 3600) -> bool:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        user_id, ts_str, signature = parts
        ts = int(ts_str)
        if int(time.time()) - ts > max_age_seconds:
            return False
        expected = hash_token(user_id, ts)
        return expected == signature
    except Exception:
        return False
