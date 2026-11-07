import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api import ws
from app.api.routes import (
    agent,
    api_keys,
    auth,
    channels,
    dashboard,
    feed,
    incidents,
    maintenance,
    metrics,
    monitors,
    notifications,
    public,
    site,
    sla,
    system,
    users,
    v1,
    workspace,
)
from app.config import settings
from app.database import engine, init_db
from app.security import require_admin, require_user
from app.seed import seed_if_empty
from app.services.cache import cache
from app.services.events import events
from app.services.scheduler import scheduler
from app.services.users import ensure_bootstrap_admin

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

API_PREFIX = "/api"
PAGE_ROUTES_BLOCKED = ("docs", "redoc", "openapi.json")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting %s v%s (%s)", settings.app_name, settings.version, settings.environment)
    await init_db()
    await ensure_bootstrap_admin()
    await cache.connect()

    if settings.seed_demo:
        try:
            seeded = await seed_if_empty()
            if seeded:
                logger.info("Demo data seeded")
        except Exception:
            logger.exception("Demo data could not be seeded")

    await events.start()
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        await events.stop()
        await cache.close()
        await engine.dispose()
        logger.info("Shutdown complete")


app = FastAPI(
    title=f"{settings.app_name} API",
    description=(
        "API uptime, response time, error rate and incident monitoring with a public "
        "status page, heartbeat monitors, alert channels and a read-only integration API."
    ),
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    if request.url.path.rstrip("/") != "/status":
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response


user_guard = [Depends(require_user)]
admin_guard = [Depends(require_admin)]

app.include_router(system.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(public.router, prefix=API_PREFIX)
app.include_router(v1.router, prefix=API_PREFIX)
app.include_router(monitors.router, prefix=API_PREFIX, dependencies=user_guard)
app.include_router(dashboard.router, prefix=API_PREFIX, dependencies=user_guard)
app.include_router(incidents.router, prefix=API_PREFIX, dependencies=user_guard)
app.include_router(notifications.router, prefix=API_PREFIX, dependencies=user_guard)
app.include_router(channels.router, prefix=API_PREFIX, dependencies=admin_guard)
app.include_router(api_keys.router, prefix=API_PREFIX, dependencies=admin_guard)
app.include_router(maintenance.router, prefix=API_PREFIX, dependencies=user_guard)
app.include_router(workspace.router, prefix=API_PREFIX, dependencies=admin_guard)
app.include_router(users.router, prefix=API_PREFIX, dependencies=admin_guard)
app.include_router(site.router, prefix=API_PREFIX)
app.include_router(feed.router, prefix=API_PREFIX)
app.include_router(sla.router, prefix=API_PREFIX)
app.include_router(agent.router, prefix=API_PREFIX)
app.include_router(metrics.router, prefix=API_PREFIX)
app.include_router(ws.router, prefix=API_PREFIX)


def mount_frontend(application: FastAPI, dist: Path) -> None:
    index_file = dist / "index.html"

    @application.get("/", include_in_schema=False)
    async def home():
        return FileResponse(index_file)

    @application.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path in PAGE_ROUTES_BLOCKED:
            raise HTTPException(status_code=404, detail="Bulunamadı")
        candidate = (dist / full_path).resolve()
        if candidate.is_file() and dist in candidate.parents:
            return FileResponse(candidate)
        if full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Bulunamadı")
        return FileResponse(index_file)


if not settings.frontend_dist:

    @app.get("/", tags=["system"])
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.version,
            "docs": "/docs",
            "health": f"{API_PREFIX}/health",
            "dashboard": f"{API_PREFIX}/dashboard",
            "status_page": f"{API_PREFIX}/status-page",
            "integration_api": f"{API_PREFIX}/v1/status",
            "auth_enabled": settings.auth_enabled,
        }

elif (Path(settings.frontend_dist) / "index.html").is_file():
    mount_frontend(app, Path(settings.frontend_dist).resolve())
else:
    logger.warning("FRONTEND_DIST is set but index.html was not found: %s", settings.frontend_dist)


@app.exception_handler(Exception)
async def unhandled_exception(_request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Beklenmeyen bir sunucu hatası oluştu"})
