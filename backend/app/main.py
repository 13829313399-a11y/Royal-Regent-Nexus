from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.carton_mark import router as carton_mark_router
from app.api.injection_schedule import router as injection_schedule_router
from app.api.iam import router as iam_router
from app.api.molding_sample import router as molding_sample_router
from app.api.pricing import router as pricing_router
from app.api.system import router as system_router
from app.core.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(carton_mark_router)
app.include_router(injection_schedule_router)
app.include_router(iam_router)
app.include_router(molding_sample_router)
app.include_router(pricing_router)
app.include_router(system_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
