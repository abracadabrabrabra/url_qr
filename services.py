import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import Link
from fastapi import HTTPException, status

settings = get_settings()


def generate_short_code() -> str:
    return "".join(
        secrets.choice(settings.short_code_alphabet)
        for _ in range(settings.short_code_length)
    )


async def get_link_by_code(session: AsyncSession, code: str) -> Link | None:
    result = await session.execute(
        select(Link).where(
            Link.short_key == code,
            Link.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def create_short_link(session: AsyncSession, original_url: str) -> Link:
    max_attempts = 10

    for _ in range(max_attempts):
        short_code = generate_short_code()
        existing_link = await get_link_by_code(session, short_code)

        if existing_link is None:
            link = Link(original_url=original_url, short_key=short_code)
            session.add(link)

            try:
                await session.commit()
                await session.refresh(link)
                return link
            except IntegrityError:
                await session.rollback()

    raise RuntimeError("Failed to generate a unique short code after multiple attempts.")


async def get_active_link_or_404(session: AsyncSession, code: str) -> Link:
    link = await get_link_by_code(session, code)

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short code not found"
        )

    return link