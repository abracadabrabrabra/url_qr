from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)


class Link(Base):
    __tablename__ = "links"

    short_key: Mapped[str] = mapped_column(String(30), primary_key=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    clicks_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
