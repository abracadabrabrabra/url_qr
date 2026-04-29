from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import io

from database import get_db
from services import create_short_link, get_link_by_code
from qr_generator import generate_simple_qr

router = APIRouter(tags=["links"])


class LinkCreate(BaseModel):
    original_url: str


class LinkResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str


@router.post(
    "/api/shorten",
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
    "/api/qr/{code}",
    summary="Get QR code for existing short URL",
    responses={
        200: {"description": "QR code image", "content": {"image/png": {}}},
        404: {"description": "Short code not found"}
    }
)
async def get_qr_for_short_url(
        code: str,
        scale: int = Query(10, ge=3, le=20, description="QR code size (3-20)"),
        session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    link = await get_link_by_code(session, code)

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    qr_bytes = generate_simple_qr(link.original_url, scale=scale)

    return StreamingResponse(
        io.BytesIO(qr_bytes),
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=qr_{code}.png"}
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
    if code.startswith("api/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid short code")

    link = await get_link_by_code(session, code)

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)