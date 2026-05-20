from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi import File, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, update, delete, select, desc
from sqlalchemy import func
from datetime import datetime
from typing import Optional
import io
import os
import tempfile
from fastapi import Form

from database import get_db
from services import create_short_link, get_link_by_code, get_active_link_or_404
from qr_generator import generate_simple_qr, generate_custom_color_qr, add_logo_to_qr, generate_qr_with_custom_params
from routers.auth import get_current_user
from models import User, Link


router = APIRouter(tags=["links"])


class LinkCreate(BaseModel):
    original_url: str


class LinkResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str
    user_id: Optional[int] = None

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
        user_id=link.user_id
    )

@router.post(
    "/api/shorten/protected",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a short URL (authenticated, linked to user)",
)
async def shorten_url_protected(
        payload: LinkCreate,
        request: Request,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
) -> LinkResponse:
    link = await create_short_link(
        session,
        str(payload.original_url),
        user_id=current_user.id
    )
    short_url = str(request.base_url).rstrip("/") + f"/{link.short_key}"

    return LinkResponse(
        original_url=link.original_url,
        short_code=link.short_key,
        short_url=short_url,
        user_id=link.user_id
    )


@router.get(
    "/api/links/{short_key}/stats",
    summary="Get full statistics for a short link (owner only)",
)
async def get_link_stats_private(
        short_key: str,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
):
    link = await get_link_by_code(session, short_key)

    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    if link.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view statistics for this link"
        )

    return {
        "short_key": link.short_key,
        "clicks_count": link.clicks_count,
        "created_at": str(link.created_at),
        "is_active": link.is_active
    }


@router.get(
    "/api/user/links",
    response_model=list[LinkResponse],
    summary="Get all links for current user",
    description="Returns all active links created by the authenticated user",
)
async def get_user_links(
        request: Request,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
        skip: int = Query(0, ge=0, description="Number of links to skip"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum number of links to return"),
        include_inactive: bool = Query(False, description="Include inactive/deleted links"),
):
    query = select(Link).where(Link.user_id == current_user.id)
    if not include_inactive:
        query = query.where(
            Link.is_active == True,
            Link.deleted_at.is_(None)
        )
    query = query.order_by(desc(Link.created_at)).offset(skip).limit(limit)
    result = await session.execute(query)
    links = result.scalars().all()
    base_url = str(request.base_url).rstrip("/")

    return [
        LinkResponse(
            original_url=link.original_url,
            short_code=link.short_key,
            short_url=f"{base_url}/{link.short_key}",
            user_id=link.user_id
        )
        for link in links
    ]


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
        request: Request,
        session: AsyncSession = Depends(get_db),
):
    if code.startswith("api/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid short code")

    link = await get_link_by_code(session, code)

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    if not link.is_active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This short link has been deactivated"
        )

    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This short link has expired"
        )

    link.clicks_count += 1

    await session.commit()

    #TODO: add record to visits table

    print(f"Redirect: {code} -> {link.original_url} (clicks: {link.clicks_count})")

    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)