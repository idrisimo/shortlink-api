import re
import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Link

ALPHABET = string.ascii_letters + string.digits
ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
RESERVED_CODES = frozenset({"api", "health", "docs", "redoc"})


def is_valid_alias(alias: str) -> bool:
    return bool(ALIAS_PATTERN.match(alias)) and alias.lower() not in RESERVED_CODES


def code_exists(db: Session, code: str) -> bool:
    return db.scalar(select(Link.id).where(Link.code == code)) is not None


def generate_code(db: Session, length: int = 7, max_attempts: int = 10) -> str:
    """Return a random unused code, retrying on the (unlikely) collision."""
    for _ in range(max_attempts):
        code = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if not code_exists(db, code):
            return code
    raise RuntimeError("Could not generate a unique short code")


def user_agent_family(user_agent: str | None) -> str:
    """Very small UA classifier; order matters (Edge/Chrome/Safari all say 'Safari')."""
    if not user_agent:
        return "Other"
    ua = user_agent.lower()
    for needle, family in (
        ("bot", "Bot"),
        ("spider", "Bot"),
        ("curl", "curl"),
        ("python-requests", "Python"),
        ("python-httpx", "Python"),
        ("edg/", "Edge"),
        ("opr/", "Opera"),
        ("firefox", "Firefox"),
        ("chrome", "Chrome"),
        ("safari", "Safari"),
    ):
        if needle in ua:
            return family
    return "Other"
