from pathlib import Path
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import settings
from app.core.auth import require_api_key
from app.core.hls_server import hls_streamer

router = APIRouter()
Auth = Annotated[str, Depends(require_api_key)]


async def _get_camera(camera_id: int) -> dict:
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    return dict(row)


def _build_rtsp_url(camera: dict) -> str:
    url = camera["rtsp_url"]
    user = camera.get("username")
    pwd = camera.get("password")
    if user and pwd and "://" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://{user}:{pwd}@{rest}"
    return url


@router.get("/{camera_id}/hls/start")
async def start_hls(camera_id: int, _: Auth):
    camera = await _get_camera(camera_id)
    rtsp_url = _build_rtsp_url(camera)
    await hls_streamer.start(camera_id, rtsp_url)
    return {"status": "started", "playlist": f"/api/streams/{camera_id}/hls/live.m3u8"}


@router.get("/{camera_id}/hls/stop")
async def stop_hls(camera_id: int, _: Auth):
    await hls_streamer.stop(camera_id)
    return {"status": "stopped"}


@router.get("/{camera_id}/hls/live.m3u8")
async def hls_playlist(camera_id: int, _: Auth):
    path = hls_streamer.playlist_path(camera_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="HLS stream not started")
    return FileResponse(path, media_type="application/vnd.apple.mpegurl")


@router.get("/{camera_id}/hls/{segment}")
async def hls_segment(camera_id: int, segment: str, _: Auth):
    if not segment.endswith(".ts"):
        raise HTTPException(status_code=400, detail="Invalid segment")
    seg_path = settings.HLS_PATH / str(camera_id) / segment
    if not seg_path.exists():
        raise HTTPException(status_code=404, detail="Segment not found")
    return FileResponse(seg_path, media_type="video/mp2t")


@router.get("/{camera_id}/rtsp-url")
async def get_rtsp_url(camera_id: int, _: Auth):
    """Returns the RTSP URL for direct player use (with credentials embedded)."""
    camera = await _get_camera(camera_id)
    return {"rtsp_url": _build_rtsp_url(camera)}


@router.get("/{camera_id}/snapshot")
async def snapshot(camera_id: int, _: Auth):
    """Grab a JPEG snapshot via FFmpeg."""
    import asyncio
    import tempfile

    camera = await _get_camera(camera_id)
    rtsp_url = _build_rtsp_url(camera)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name

    cmd = [
        settings.FFMPEG_BIN,
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        tmp,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=15)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail="Snapshot timeout")

    if not Path(tmp).exists():
        raise HTTPException(status_code=500, detail="Snapshot failed")

    return FileResponse(tmp, media_type="image/jpeg")
