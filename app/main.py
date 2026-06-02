import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import cameras, recordings, streams, events
from app.core.database import init_db
from app.core.recorder import RecorderManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    recorder = RecorderManager()
    app.state.recorder = recorder
    await recorder.start_all()
    logger.info("freeNVR started")
    yield
    await recorder.stop_all()
    logger.info("freeNVR stopped")


app = FastAPI(title="freeNVR", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
app.include_router(recordings.router, prefix="/api/recordings", tags=["recordings"])
app.include_router(streams.router, prefix="/api/streams", tags=["streams"])
app.include_router(events.router, prefix="/api/events", tags=["events"])

app.mount("/recordings", StaticFiles(directory="recordings"), name="recordings")
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
