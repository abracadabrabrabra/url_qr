from fastapi import FastAPI

from config import get_settings
from routers.links import router as links_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(links_router)


@app.get("/api/health", tags=["health"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
