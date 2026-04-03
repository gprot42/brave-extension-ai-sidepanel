"""FastAPI application with lifespan for BLE connection and sync tasks."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — initialize database; BLE connects on-demand via POST /api/connect
    await init_db()
    await init_cloud_client()
    logger = logging.getLogger(__name__)
    logger.info("Database initialized. Use POST /api/connect to connect to the Helio Strap.")

    yield

    # Shutdown
    await connection.disconnect()


app = FastAPI(title="Helio Strap Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(ws_router)
