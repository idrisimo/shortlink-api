from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey, Click, Link, as_utc, utcnow
from app.ratelimit import limit_link_creation
from app.schemas import (
    DailyClicks,
    ErrorOut,
    LinkCreate,
    LinkOut,
    LinkPage,
    LinkStats,
    LinkUpdate,
    ReferrerCount,
)
from app.security import get_current_key
from app.services.codes import code_exists, generate_code, is_valid_alias

router = APIRouter(
    prefix="/api/links",
    tags=["links"],
    responses={401: {"model": ErrorOut, "description": "Missing or invalid API key"}},
)

STATS_DAYS = 30
TOP_REFERRERS = 5


def _to_out(link: Link, request: Request) -> LinkOut:
    base = request.app.state.settings.base_url.rstrip("/")
    return LinkOut(
        code=link.code,
        short_url=f"{base}/{link.code}",
        target_url=link.target_url,
        created_at=as_utc(link.created_at),
        expires_at=as_utc(link.expires_at) if link.expires_at else None,
    )


def _get_owned_link(db: Session, code: str, key: ApiKey) -> Link:
    """Other callers' links look exactly like missing ones (404, not 403)."""
    link = db.scalar(select(Link).where(Link.code == code, Link.owner_id == key.id))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return link


@router.post(
    "",
    response_model=LinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a short link",
    responses={
        409: {"model": ErrorOut, "description": "Alias already in use"},
        422: {"description": "Validation error (bad URL, alias or expiry)"},
        429: {"model": ErrorOut, "description": "Rate limit exceeded"},
    },
)
def create_link(
    payload: LinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(limit_link_creation),
) -> LinkOut:
    if payload.alias is not None:
        if not is_valid_alias(payload.alias):
            raise HTTPException(
                422,
                "Alias must be 3-32 characters of letters, digits, '_' or '-' and not reserved",
            )
        if code_exists(db, payload.alias):
            raise HTTPException(status.HTTP_409_CONFLICT, "Alias already in use")
        code = payload.alias
    else:
        code = generate_code(db, request.app.state.settings.code_length)

    link = Link(
        code=code,
        target_url=str(payload.url),
        owner_id=key.id,
        expires_at=payload.expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _to_out(link, request)


@router.get("", response_model=LinkPage, summary="List your links")
def list_links(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    key: ApiKey = Depends(get_current_key),
) -> LinkPage:
    total = db.scalar(select(func.count()).select_from(Link).where(Link.owner_id == key.id)) or 0
    rows = db.scalars(
        select(Link)
        .where(Link.owner_id == key.id)
        .order_by(Link.created_at.desc(), Link.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return LinkPage(
        items=[_to_out(row, request) for row in rows], total=total, limit=limit, offset=offset
    )


@router.get(
    "/{code}",
    response_model=LinkOut,
    summary="Get one link",
    responses={404: {"model": ErrorOut, "description": "Unknown link"}},
)
def get_link(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(get_current_key),
) -> LinkOut:
    return _to_out(_get_owned_link(db, code, key), request)


@router.patch(
    "/{code}",
    response_model=LinkOut,
    summary="Update a link's target or expiry",
    responses={404: {"model": ErrorOut, "description": "Unknown link"}},
)
def update_link(
    code: str,
    payload: LinkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(get_current_key),
) -> LinkOut:
    link = _get_owned_link(db, code, key)
    if "url" in payload.model_fields_set and payload.url is not None:
        link.target_url = str(payload.url)
    if "expires_at" in payload.model_fields_set:
        link.expires_at = payload.expires_at
    db.commit()
    db.refresh(link)
    return _to_out(link, request)


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a link and its click history",
    responses={404: {"model": ErrorOut, "description": "Unknown link"}},
)
def delete_link(
    code: str,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(get_current_key),
) -> Response:
    db.delete(_get_owned_link(db, code, key))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{code}/stats",
    response_model=LinkStats,
    summary="Click analytics for a link",
    responses={404: {"model": ErrorOut, "description": "Unknown link"}},
)
def link_stats(
    code: str,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(get_current_key),
) -> LinkStats:
    link = _get_owned_link(db, code, key)
    total = db.scalar(select(func.count()).select_from(Click).where(Click.link_id == link.id)) or 0

    today = utcnow().date()
    start_day = today - timedelta(days=STATS_DAYS - 1)
    recent = db.scalars(
        select(Click.clicked_at).where(
            Click.link_id == link.id,
            Click.clicked_at >= utcnow() - timedelta(days=STATS_DAYS),
        )
    ).all()
    per_day = Counter(as_utc(ts).date() for ts in recent)
    series = [
        DailyClicks(date=day, clicks=per_day.get(day, 0))
        for day in (start_day + timedelta(days=i) for i in range(STATS_DAYS))
    ]

    referrer_rows = db.execute(
        select(Click.referrer, func.count().label("n"))
        .where(Click.link_id == link.id)
        .group_by(Click.referrer)
        .order_by(func.count().desc(), Click.referrer)
        .limit(TOP_REFERRERS)
    ).all()
    top = [ReferrerCount(referrer=ref or "(direct)", clicks=n) for ref, n in referrer_rows]

    return LinkStats(code=link.code, total_clicks=total, clicks_per_day=series, top_referrers=top)
