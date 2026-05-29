from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, update, delete, select
from config import get_settings
from models import RefreshToken, User
import hashlib


settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

async def save_refresh_token(
        session: AsyncSession,
        user_id: int,
        refresh_token: str,
        expires_days: int,
        user_agent: str = None,
        ip_address: str = None
) -> RefreshToken:
    token_hash = hash_token(refresh_token)
    expires_at = datetime.utcnow() + timedelta(days=expires_days)

    token_record = RefreshToken(
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires_at,
        revoked=False,
        user_agent=user_agent,
        ip_address=ip_address
    )
    session.add(token_record)
    await session.commit()
    await session.refresh(token_record)
    return token_record


async def validate_refresh_token(
        session: AsyncSession,
        refresh_token: str
) -> tuple[User | None, RefreshToken | None]:
    token_hash = hash_token(refresh_token)

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None, None

    result = await session.execute(
        select(RefreshToken, User)
        .join(User, RefreshToken.user_id == User.id)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.utcnow(),
            User.is_active == True
        )
    )

    row = result.first()
    if row:
        return row.User, row.RefreshToken
    return None, None


async def revoke_refresh_token(
        session: AsyncSession,
        refresh_token: str
) -> bool:
    token_hash = hash_token(refresh_token)
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .values(revoked=True)
    )
    await session.commit()
    return result.rowcount > 0


async def revoke_all_user_tokens(
        session: AsyncSession,
        user_id: int,
        exclude_token_hash: str = None
) -> int:
    query = update(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False
    )
    if exclude_token_hash:
        query = query.where(RefreshToken.token_hash != exclude_token_hash)

    result = await session.execute(query.values(revoked=True))
    await session.commit()
    return result.rowcount


async def cleanup_expired_tokens(session: AsyncSession) -> int:
    result = await session.execute(
        delete(RefreshToken).where(RefreshToken.expires_at <= datetime.utcnow())
    )
    await session.commit()
    return result.rowcount


async def update_token_last_used(
        session: AsyncSession,
        token_record: RefreshToken,
        ip_address: str = None
):
    token_record.last_used_at = datetime.utcnow()
    if ip_address:
        token_record.ip_address = ip_address
    await session.commit()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    print(f"DEBUG: password type = {type(password)}")
    print(f"DEBUG: password value = {password}")
    print(f"DEBUG: password length = {len(password) if password else 0}")

    if not password:
        raise ValueError("Password cannot be empty")

    if len(password) > 72:
        password = password[:72]
        print(f"DEBUG: Password truncated to 72 bytes")

    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_key, algorithm=settings.algorithm)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_key, algorithm=settings.algorithm)

def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user