from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi import File, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, update, delete, insert, select, desc, cast, String
from sqlalchemy import func
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urlparse
import io
import os
import tempfile
from fastapi import Form

from database import AsyncSessionLocal, get_db
from services import create_short_link, generate_short_code, get_link_by_code, get_active_link_or_404
from qr_generator import generate_simple_qr, generate_custom_color_qr, add_logo_to_qr, generate_qr_with_custom_params
from routers.auth import get_current_user
from models import User, Link, Visit


router = APIRouter(tags=["links"])
SHORT_LINK_PREFIX = "/r"


class LinkCreate(BaseModel):
    original_url: str


class LinkResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str
    user_id: Optional[int] = None

class LinkStatsResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str
    user_id: Optional[int] = None
    clicks_count: int
    created_at: str
    is_active: bool


class UserStatsResponse(BaseModel):
    total_links: int
    total_clicks: int
    clicks_today: int
    clicks_this_month: int


class DailyClicksResponse(BaseModel):
    date: str
    clicks: int


class AnalyticsComparisonResponse(BaseModel):
    total_clicks_percent: int
    unique_clicks_percent: int
    average_per_day_percent: int


class LinkAnalyticsResponse(BaseModel):
    short_key: str
    short_url: str
    original_url: str
    total_clicks: int
    unique_clicks: int
    average_per_day: int
    last_click_at: str | None
    created_at: str
    is_active: bool
    daily_clicks: list[DailyClicksResponse]
    comparison: AnalyticsComparisonResponse


class LinkDeleteResponse(BaseModel):
    msg: str
    short_key: str
    is_active: bool
    deleted_at: str | None


class LinkUpdateResponse(BaseModel):
    old_short_key: str
    short_key: str
    short_url: str
    original_url: str
    clicks_count: int
    created_at: str
    is_active: bool


class QRColorRequest(BaseModel):
    dark_color: str = "#000000"
    light_color: str = "#FFFFFF"
    scale: int = 10


def get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip

    return request.client.host if request.client else None


def build_short_url(request: Request, short_key: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}{SHORT_LINK_PREFIX}/{short_key}"


def detect_device_type(user_agent: str | None) -> str | None:
    if not user_agent:
        return None

    value = user_agent.lower()
    if any(marker in value for marker in ("mobile", "iphone", "android")):
        return "mobile"
    if any(marker in value for marker in ("ipad", "tablet")):
        return "tablet"
    if any(marker in value for marker in ("bot", "crawler", "spider")):
        return "bot"
    return "desktop"


def detect_browser(user_agent: str | None) -> str | None:
    if not user_agent:
        return None

    value = user_agent.lower()
    if "yabrowser/" in value:
        return "yandex"
    if "edg/" in value:
        return "edge"
    if "opr/" in value or "opera" in value:
        return "opera"
    if "firefox/" in value:
        return "firefox"
    if "chrome/" in value or "chromium/" in value:
        return "chrome"
    if "safari/" in value:
        return "safari"
    return "other"


def calculate_percent_change(current: int, previous: int) -> int:
    if previous == 0:
        return 0 if current == 0 else 100

    return round(((current - previous) / previous) * 100)


async def generate_unique_short_key(session: AsyncSession) -> str:
    max_attempts = 10
    for _ in range(max_attempts):
        short_key = generate_short_code()
        result = await session.execute(select(Link).where(Link.short_key == short_key))
        if result.scalar_one_or_none() is None:
            return short_key

    raise RuntimeError("Failed to generate a unique short code after multiple attempts.")


def is_valid_domain(hostname: str) -> bool:
    labels = hostname.rstrip(".").split(".")
    if len(labels) < 2:
        return False

    if len(labels[-1]) < 2 or not labels[-1].isalpha():
        return False

    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not all(char.isalnum() or char == "-" for char in label):
            return False

    return True


def validate_original_url(original_url: str) -> str:
    url = original_url.strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL cannot be empty",
        )

    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must be valid and include scheme and host",
        )

    if parsed_url.scheme.lower() not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http and https URLs are allowed",
        )

    if not parsed_url.hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must include a valid host",
        )

    if not is_valid_domain(parsed_url.hostname.lower()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL host must be a valid domain",
        )

    return url


async def record_visit_background(
        short_key: str,
        ip_address: str | None,
        user_agent: str | None,
        referer: str | None,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Visit(
                short_key=short_key,
                visited_at=datetime.utcnow(),
                ip_address=ip_address,
                user_agent=user_agent,
                referer=referer,
                device_type=detect_device_type(user_agent),
                browser=detect_browser(user_agent),
            )
        )
        await session.commit()


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
    original_url = validate_original_url(payload.original_url)
    link = await create_short_link(session, original_url)
    short_url = build_short_url(request, link.short_key)

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
    original_url = validate_original_url(payload.original_url)
    link = await create_short_link(
        session,
        original_url,
        user_id=current_user.id
    )
    short_url = build_short_url(request, link.short_key)

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

    clicks_result = await session.execute(
        select(func.count(Visit.id)).where(Visit.short_key == link.short_key)
    )

    return {
        "short_key": link.short_key,
        "clicks_count": int(clicks_result.scalar_one()),
        "created_at": str(link.created_at),
        "is_active": link.is_active
    }


@router.get(
    "/api/links/{short_key}/analytics",
    response_model=LinkAnalyticsResponse,
    summary="Get detailed analytics for a short link (owner only)",
)
async def get_link_analytics(
        short_key: str,
        request: Request,
        date_from: date = Query(..., description="Start date in YYYY-MM-DD format"),
        date_to: date = Query(..., description="End date in YYYY-MM-DD format"),
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
) -> LinkAnalyticsResponse:
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be less than or equal to date_to",
        )

    result = await session.execute(select(Link).where(Link.short_key == short_key))
    link = result.scalar_one_or_none()

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    if link.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view analytics for this link",
        )

    period_days = (date_to - date_from).days + 1
    current_start = datetime.combine(date_from, datetime.min.time())
    current_end = datetime.combine(date_to + timedelta(days=1), datetime.min.time())
    previous_start = current_start - timedelta(days=period_days)
    previous_end = current_start

    unique_visitor_key = func.concat(
        func.coalesce(cast(Visit.ip_address, String), ""),
        "|",
        func.coalesce(Visit.user_agent, ""),
    )

    async def get_period_metrics(start_at: datetime, end_at: datetime) -> dict[str, int | datetime | None]:
        metrics_result = await session.execute(
            select(
                func.count(Visit.id),
                func.count(func.distinct(unique_visitor_key)),
                func.max(Visit.visited_at),
            ).where(
                Visit.short_key == short_key,
                Visit.visited_at >= start_at,
                Visit.visited_at < end_at,
            )
        )
        total_clicks, unique_clicks, last_click_at = metrics_result.one()

        return {
            "total_clicks": int(total_clicks),
            "unique_clicks": int(unique_clicks),
            "last_click_at": last_click_at,
        }

    current_metrics = await get_period_metrics(current_start, current_end)
    previous_metrics = await get_period_metrics(previous_start, previous_end)

    daily_result = await session.execute(
        select(
            func.date(Visit.visited_at).label("visit_date"),
            func.count(Visit.id).label("clicks"),
        )
        .where(
            Visit.short_key == short_key,
            Visit.visited_at >= current_start,
            Visit.visited_at < current_end,
        )
        .group_by(func.date(Visit.visited_at))
    )
    daily_counts = {
        str(visit_date): int(clicks)
        for visit_date, clicks in daily_result.all()
    }

    daily_clicks = [
        DailyClicksResponse(
            date=str(date_from + timedelta(days=day_offset)),
            clicks=daily_counts.get(str(date_from + timedelta(days=day_offset)), 0),
        )
        for day_offset in range(period_days)
    ]

    total_clicks = int(current_metrics["total_clicks"])
    unique_clicks = int(current_metrics["unique_clicks"])
    average_per_day = total_clicks // period_days
    previous_average_per_day = int(previous_metrics["total_clicks"]) // period_days
    last_click_at = current_metrics["last_click_at"]
    return LinkAnalyticsResponse(
        short_key=link.short_key,
        short_url=build_short_url(request, link.short_key),
        original_url=link.original_url,
        total_clicks=total_clicks,
        unique_clicks=unique_clicks,
        average_per_day=average_per_day,
        last_click_at=last_click_at.isoformat() if isinstance(last_click_at, datetime) else None,
        created_at=link.created_at.isoformat(),
        is_active=link.is_active,
        daily_clicks=daily_clicks,
        comparison=AnalyticsComparisonResponse(
            total_clicks_percent=calculate_percent_change(total_clicks, int(previous_metrics["total_clicks"])),
            unique_clicks_percent=calculate_percent_change(unique_clicks, int(previous_metrics["unique_clicks"])),
            average_per_day_percent=calculate_percent_change(average_per_day, previous_average_per_day),
        ),
    )


@router.get(
    "/api/user/stats",
    response_model=UserStatsResponse,
    summary="Get dashboard statistics for current user",
)
async def get_user_stats(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    active_user_links_filter = (
        Link.user_id == current_user.id,
        Link.is_active == True,
        Link.deleted_at.is_(None),
    )

    links_result = await session.execute(
        select(func.count(Link.short_key)).where(*active_user_links_filter)
    )
    total_links = links_result.scalar_one()

    clicks_result = await session.execute(
        select(func.count(Visit.id))
        .join(Link, Visit.short_key == Link.short_key)
        .where(*active_user_links_filter)
    )
    total_clicks = clicks_result.scalar_one()

    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)

    async def count_visits_since(start_at: datetime) -> int:
        result = await session.execute(
            select(func.count(Visit.id))
            .join(Link, Visit.short_key == Link.short_key)
            .where(
                *active_user_links_filter,
                Visit.visited_at >= start_at,
            )
        )
        return int(result.scalar_one())

    return UserStatsResponse(
        total_links=int(total_links),
        total_clicks=int(total_clicks),
        clicks_today=await count_visits_since(today_start),
        clicks_this_month=await count_visits_since(month_start),
    )


@router.get(
    "/api/user/links",
    response_model=list[LinkStatsResponse],
    summary="Get all links for current user with statistics",
)
async def get_user_links(
        request: Request,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
        skip: int = Query(0, ge=0, description="Number of links to skip"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum number of links to return"),
        include_inactive: bool = Query(False, description="Include inactive/deleted links"),
):
    conditions = [Link.user_id == current_user.id]
    if not include_inactive:
        conditions.extend((
            Link.is_active == True,
            Link.deleted_at.is_(None)
        ))
    clicks_count_subquery = (
        select(func.count(Visit.id))
        .where(Visit.short_key == Link.short_key)
        .correlate(Link)
        .scalar_subquery()
    )
    result = await session.execute(
        select(Link, clicks_count_subquery.label("clicks_count"))
        .where(*conditions)
        .order_by(desc(Link.created_at))
        .offset(skip)
        .limit(limit)
    )
    links_with_clicks = result.all()

    return [
        LinkStatsResponse(
            original_url=link.original_url,
            short_code=link.short_key,
            short_url=build_short_url(request, link.short_key),
            user_id=link.user_id,
            clicks_count=int(clicks_count),
            created_at=str(link.created_at),
            is_active=link.is_active
        )
        for link, clicks_count in links_with_clicks
    ]


@router.patch(
    "/api/links/{short_key}",
    response_model=LinkUpdateResponse,
    summary="Regenerate a short code without losing statistics (owner only)",
)
async def update_user_link(
        short_key: str,
        request: Request,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
) -> LinkUpdateResponse:
    result = await session.execute(select(Link).where(Link.short_key == short_key))
    link = result.scalar_one_or_none()

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    if link.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this link",
        )

    if not link.is_active or link.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Deleted or inactive links cannot be updated",
        )

    old_short_key = link.short_key
    new_short_key = await generate_unique_short_key(session)

    await session.execute(
        insert(Link).values(
            short_key=new_short_key,
            original_url=link.original_url,
            user_id=link.user_id,
            created_at=link.created_at,
            expires_at=link.expires_at,
            clicks_count=0,
            is_active=link.is_active,
            deleted_at=link.deleted_at,
        )
    )
    await session.execute(
        update(Visit)
        .where(Visit.short_key == old_short_key)
        .values(short_key=new_short_key)
    )
    await session.execute(delete(Link).where(Link.short_key == old_short_key))
    await session.commit()

    updated_result = await session.execute(select(Link).where(Link.short_key == new_short_key))
    updated_link = updated_result.scalar_one()
    clicks_result = await session.execute(
        select(func.count(Visit.id)).where(Visit.short_key == new_short_key)
    )

    return LinkUpdateResponse(
        old_short_key=old_short_key,
        short_key=updated_link.short_key,
        short_url=build_short_url(request, updated_link.short_key),
        original_url=updated_link.original_url,
        clicks_count=int(clicks_result.scalar_one()),
        created_at=updated_link.created_at.isoformat(),
        is_active=updated_link.is_active,
    )


@router.delete(
    "/api/links/{short_key}",
    response_model=LinkDeleteResponse,
    summary="Soft delete a short link (owner only)",
)
async def delete_user_link(
        short_key: str,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
) -> LinkDeleteResponse:
    result = await session.execute(select(Link).where(Link.short_key == short_key))
    link = result.scalar_one_or_none()

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short code not found")

    if link.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this link",
        )

    if not link.is_active and link.deleted_at is not None:
        return LinkDeleteResponse(
            msg="Link already deleted",
            short_key=link.short_key,
            is_active=link.is_active,
            deleted_at=link.deleted_at.isoformat(),
        )

    link.is_active = False
    link.deleted_at = datetime.utcnow()
    await session.commit()
    await session.refresh(link)

    return LinkDeleteResponse(
        msg="Link deleted successfully",
        short_key=link.short_key,
        is_active=link.is_active,
        deleted_at=link.deleted_at.isoformat() if link.deleted_at else None,
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
    f"{SHORT_LINK_PREFIX}/{{code}}",
    summary="Redirect by short code",
    responses={404: {"description": "Short code not found"}},
)
async def redirect_to_original(
        code: str,
        request: Request,
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(get_db),
):
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

    user_agent = request.headers.get("user-agent")
    background_tasks.add_task(
        record_visit_background,
        link.short_key,
        get_client_ip(request),
        user_agent,
        request.headers.get("referer"),
    )

    ##print(f"Redirect: {code} -> {link.original_url}")

    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
