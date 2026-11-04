import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

MAX_URL_LENGTH = 2048


def _require_future(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return value
    aware = value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value
    if aware <= dt.datetime.now(dt.UTC):
        raise ValueError("expires_at must be in the future")
    return value


def _limit_url_length(value: HttpUrl | None) -> HttpUrl | None:
    if value is not None and len(str(value)) > MAX_URL_LENGTH:
        raise ValueError(f"url must be at most {MAX_URL_LENGTH} characters")
    return value


class LinkCreate(BaseModel):
    url: HttpUrl = Field(description="Destination URL (http or https only).")
    alias: str | None = Field(
        default=None,
        description="Optional custom code: 3-32 characters of letters, digits, '_' or '-'.",
    )
    expires_at: dt.datetime | None = Field(
        default=None, description="Optional expiry time (ISO 8601). Must be in the future."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "url": "https://example.com/some/very/long/path?utm_source=newsletter",
                    "alias": "launch",
                    "expires_at": "2030-01-01T00:00:00Z",
                }
            ]
        }
    )

    _check_url = field_validator("url")(_limit_url_length)
    _check_expiry = field_validator("expires_at")(_require_future)


class LinkUpdate(BaseModel):
    url: HttpUrl | None = Field(default=None, description="New destination URL.")
    expires_at: dt.datetime | None = Field(
        default=None, description="New expiry time; send null to remove the expiry."
    )

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"url": "https://example.org/new-target"}]}
    )

    _check_url = field_validator("url")(_limit_url_length)
    _check_expiry = field_validator("expires_at")(_require_future)


class LinkOut(BaseModel):
    code: str
    short_url: str
    target_url: str
    created_at: dt.datetime
    expires_at: dt.datetime | None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "launch",
                    "short_url": "http://localhost:8000/launch",
                    "target_url": "https://example.com/some/very/long/path",
                    "created_at": "2026-11-04T10:00:00Z",
                    "expires_at": None,
                }
            ]
        }
    )


class LinkPage(BaseModel):
    items: list[LinkOut]
    total: int
    limit: int
    offset: int


class DailyClicks(BaseModel):
    date: dt.date
    clicks: int


class ReferrerCount(BaseModel):
    referrer: str
    clicks: int


class LinkStats(BaseModel):
    code: str
    total_clicks: int
    clicks_per_day: list[DailyClicks] = Field(description="Last 30 days, oldest first.")
    top_referrers: list[ReferrerCount]


class ErrorOut(BaseModel):
    detail: str
