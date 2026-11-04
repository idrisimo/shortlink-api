from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Click, Link
from app.schemas import ErrorOut
from app.services.codes import user_agent_family

router = APIRouter(tags=["redirect"])


@router.get(
    "/{code}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Follow a short link",
    response_class=RedirectResponse,
    responses={
        307: {"description": "Redirect to the target URL; the click is recorded"},
        404: {"model": ErrorOut, "description": "Unknown or expired code"},
    },
)
def follow_link(code: str, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    link = db.scalar(select(Link).where(Link.code == code))
    if link is None or link.is_expired:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found or expired")
    db.add(
        Click(
            link_id=link.id,
            referrer=request.headers.get("referer"),
            user_agent_family=user_agent_family(request.headers.get("user-agent")),
        )
    )
    db.commit()
    return RedirectResponse(link.target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
