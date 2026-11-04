from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo; treat naive values as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    links: Mapped[list["Link"]] = relationship(back_populates="owner")


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    owner_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    owner: Mapped[ApiKey] = relationship(back_populates="links")
    clicks: Mapped[list["Click"]] = relationship(
        back_populates="link", cascade="all, delete-orphan"
    )

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and as_utc(self.expires_at) <= utcnow()


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id"), index=True)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    referrer: Mapped[str | None] = mapped_column(String(2048), default=None)
    user_agent_family: Mapped[str] = mapped_column(String(50), default="Other")

    link: Mapped[Link] = relationship(back_populates="clicks")
