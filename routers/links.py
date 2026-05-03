from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi import File, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import io
import os
import tempfile
from fastapi import Form

from database import get_db
from services import create_short_link, get_link_by_code, get_active_link_or_404
from qr_generator import generate_simple_qr, generate_custom_color_qr, add_logo_to_qr, generate_qr_with_custom_params

router = APIRouter(tags=["links"])


class LinkCreate(BaseModel):
    original_url: str


class LinkResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str

class QRColorRequest(BaseModel):
    dark_color: str = "#000000"
    light_color: str = "#FFFFFF"
    scale: int = 10

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

@router.post(
    "/api/qr/{code}/custom",
    summary="Generate QR with all options (colors, logo)"
)
async def get_custom_qr_for_short_url(
        code: str,
        session: AsyncSession = Depends(get_db),
        dark_color: Optional[str] = Form(None),
        light_color: Optional[str] = Form(None),
        use_default_logo: bool = Form(False),
        scale: int = Form(10, ge=3, le=20),
        logo_file: Optional[UploadFile] = File(None),
) -> StreamingResponse:
    link = await get_active_link_or_404(session, code)

    if dark_color:
        if not dark_color.startswith('#') or len(dark_color) != 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dark_color must be in format #RRGGBB"
            )
        try:
            int(dark_color[1:], 16)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dark_color must be valid hex color"
            )

    if light_color:
        if not light_color.startswith('#') or len(light_color) != 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="light_color must be in format #RRGGBB"
            )
        try:
            int(light_color[1:], 16)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="light_color must be valid hex color"
            )

    logo_path = None

    if logo_file and logo_file.filename:
        if not logo_file.content_type in ["image/png", "image/jpeg", "image/jpg"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PNG and JPEG images are allowed for logo"
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            content = await logo_file.read()
            tmp_file.write(content)
            logo_path = tmp_file.name
    elif use_default_logo:
        default_logo_path = "static_data/logo.png"
        if os.path.exists(default_logo_path):
            logo_path = default_logo_path

    try:
        qr_bytes = generate_qr_with_custom_params(
            url=link.original_url,
            scale=scale,
            dark_color=dark_color,
            light_color=light_color,
            logo_path=logo_path
        )
    finally:
        if logo_file and logo_file.filename and logo_path and os.path.exists(logo_path):
            os.unlink(logo_path)

    return StreamingResponse(
        io.BytesIO(qr_bytes),
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=qr_{code}_custom.png"}
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
    link = await get_active_link_or_404(session, code)
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