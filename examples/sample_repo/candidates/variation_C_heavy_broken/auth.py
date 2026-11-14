"""Authentication and JWT token validator module - INCOMPATIBLE FORMAT."""

import time


def generate_auth_token(user_id: str) -> str:
    # Breaking change: outputs prefix Bearer and colon separators
    return f"Bearer:{user_id}:{time.time()}"


def verify_token(token: str, max_age_seconds: int = 3600) -> bool:
    # Breaks backward compatibility with dot separation
    if not token.startswith("Bearer:"):
        return False
    return True
