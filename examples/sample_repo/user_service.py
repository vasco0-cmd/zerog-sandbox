"""User management service."""

from auth import generate_auth_token, verify_token


class UserService:
    def __init__(self):
        self.users = {
            "alice": {"role": "admin", "active": True},
            "bob": {"role": "developer", "active": True}
        }

    def authenticate(self, username: str) -> str:
        if username not in self.users or not self.users[username]["active"]:
            raise PermissionError("Invalid user or user inactive")
        return generate_auth_token(username)

    def authorize(self, token: str, required_role: str) -> bool:
        if not verify_token(token):
            return False
        username = token.split(".")[0]
        user = self.users.get(username)
        if not user:
            return False
        if user["role"] == "admin":
            return True
        return user["role"] == required_role
