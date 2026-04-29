from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services import create_short_link, get_link_by_code

router = APIRouter(tags=["links"])


class LinkCreate(BaseModel):
    original_url: str


class LinkResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str


@router.post(
    "/shorten",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a short URL",
)
async def shorten_url(
    payload: LinkCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LinkResponse:
    link = await create_short_link(session, str(payload.original_url))
    short_url = str(request.base_url).rstrip("/") + f"/{link.short_key}"

    return LinkResponse(
        original_url=link.original_url,
        short_code=link.short_key,
        short_url=short_url,
    )


@router.get(
    "/{code}",
    summary="Redirect by short code",
    responses={404: {"description": "Short code not found"}},
)
async def redirect_to_original(
    code: str,
    session: AsyncSession = Depends(get_db),
):
    link = await get_link_by_code(session, code)

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
