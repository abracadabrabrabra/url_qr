from fastapi import FastAPI

from config import get_settings
from routers.links import router as links_router
from routers.auth import router as auth_router
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from auth_services import cleanup_expired_tokens

async def cleanup_expired_tokens_job():
    async with AsyncSessionLocal() as session:
        count = await cleanup_expired_tokens(session)
        if count:
            print(f"Cleaned up {count} expired refresh tokens")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_expired_tokens_job, 'interval', hours=24)
    scheduler.start()
    yield
    scheduler.shutdown()

settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(links_router)
app.include_router(auth_router)


@app.get("/api/health", tags=["health"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
