"""FastAPI application with lifespan for BLE connection and sync tasks."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.config import PERIODIC_SYNC_INTERVAL
from backend.data.database import init_db
from backend.data.sync import periodic_sync_loop, start_realtime_hr, init_cloud_client
from backend.ble.connection import connection
from backend.api.routes import router
from backend.api.websocket import ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Prevent browser/proxy caching on all API responses."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — initialize database; BLE connects on-demand via POST /api/connect
    await init_db()
    await init_cloud_client()
    logger = logging.getLogger(__name__)
    logger.info("Database initialized. Use POST /api/connect to connect to the Helio Strap.")

    yield

    # Shutdown
    logger.info("Shutting down...")
    
    # Cancel background tasks
    from backend.api.routes import _sync_task, _cloud_login_task
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        try:
            await asyncio.wait_for(_sync_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    
    if _cloud_login_task and not _cloud_login_task.done():
        _cloud_login_task.cancel()
        try:
            await asyncio.wait_for(_cloud_login_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    
    # Disconnect BLE with timeout
    try:
        await asyncio.wait_for(connection.disconnect(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("BLE disconnect timed out, forcing exit")
    
    logger.info("Shutdown complete")


app = FastAPI(title="Helio Strap Dashboard", lifespan=lifespan)

app.add_middleware(NoCacheMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(ws_router)

_logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return detailed error info for unhandled exceptions instead of generic 500."""
    _logger.error("Unhandled %s on %s: %s", type(exc).__name__, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )
