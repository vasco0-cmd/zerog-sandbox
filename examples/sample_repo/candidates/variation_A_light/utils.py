"""Formatting and string helpers."""


def format_username(username: str) -> str:
    return username.strip().lower()


def sanitize_input(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
