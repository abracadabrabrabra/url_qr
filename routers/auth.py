from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from database import get_db
from auth_services import authenticate_user, create_access_token, create_refresh_token, decode_token, get_password_hash
from auth_services import hash_token, save_refresh_token, validate_refresh_token, revoke_refresh_token, revoke_all_user_tokens
from auth_services import update_token_last_used, cleanup_expired_tokens
from models import RefreshToken, User
from config import get_settings
from typing import Dict, Any
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()
security = HTTPBearer()

class UserCreate(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
        user_data: UserCreate,
        session: AsyncSession = Depends(get_db)
):
    try:
        print(f"DEBUG: Trying to register user {user_data.email}")

        result = await session.execute(
            select(User).where(User.email == user_data.email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        hashed_password = get_password_hash(user_data.password)
        print(f"DEBUG: Password hashed successfully")

        new_user = User(
            email=user_data.email,
            password_hash=hashed_password,
            is_active=True
        )

        session.add(new_user)
        print(f"DEBUG: User added to session, attempting commit...")

        await session.commit()
        print(f"DEBUG: Commit successful")

        await session.refresh(new_user)
        print(f"DEBUG: User refreshed, id = {new_user.id}")

        return {
            "msg": "User created successfully",
            "user_id": new_user.id,
            "email": new_user.email
        }

    except IntegrityError as e:
        await session.rollback()
        print(f"DEBUG: IntegrityError: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database error: could not create user"
        )
    except Exception as e:
        await session.rollback()
        print(f"DEBUG: Unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/login")
async def login(
        request: Request,
        response: Response,
        form_data: OAuth2PasswordRequestForm = Depends(),
        session: AsyncSession = Depends(get_db)
):
    try:
        user = await authenticate_user(session, form_data.username, form_data.password)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        token_data = {"sub": user.email, "user_id": user.id}
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        user_agent = request.headers.get("user-agent")
        client_ip = request.client.host if request.client else None
        await save_refresh_token(
            session,
            user.id,
            refresh_token,
            settings.refresh_token_expire_days,
            user_agent,
            client_ip
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    except Exception as e:
        print(f"ERROR in login: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise


@router.post("/refresh")
async def refresh_tokens(
        refresh_request: dict,
        request: Request,
        session: AsyncSession = Depends(get_db)
):
    refresh_token = refresh_request.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required"
        )

    user, token_record = await validate_refresh_token(session, refresh_token)
    if not user or not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    client_ip = request.client.host if request.client else None
    await update_token_last_used(session, token_record, client_ip)
    token_data = {"sub": user.email, "user_id": user.id}
    new_access_token = create_access_token(data=token_data)

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/logout")
async def logout(
        logout_request: dict,
        response: Response,
        session: AsyncSession = Depends(get_db)
):
    refresh_token = logout_request.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token required"
        )

    user, token_record = await validate_refresh_token(session, refresh_token)

    if not user or not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    await revoke_refresh_token(session, refresh_token)

    response.delete_cookie("refresh_token")
    return {"msg": "Successfully logged out"}


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        session: AsyncSession = Depends(get_db)
) -> User:
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    email = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    return user


@router.post("/logout-all")
async def logout_all_devices(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db)
):
    count = await revoke_all_user_tokens(session, current_user.id)
    return {
        "msg": f"Successfully logged out from all {count} devices"
    }


@router.get("/protected")
async def protected_endpoint(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return {
        "message": f"Hello {current_user.email}, you have access to protected data!",
        "user_id": current_user.id,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "created_at": str(current_user.created_at)
    }

