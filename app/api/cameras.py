from datetime import datetime, UTC
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.core.auth import require_api_key
from app.models import CameraCreate, CameraOut, CameraUpdate

router = APIRouter()
Auth = Annotated[str, Depends(require_api_key)]

_CAM_DEFAULTS = {
    "status": "stopped",
    "detection_mode": "ffmpeg",
    "onvif_host": None,
    "onvif_port": 8000,
    "onvif_events": 0,
}


def _normalize(row: dict) -> dict:
    d = {**_CAM_DEFAULTS, **row}
    d.setdefault("created_at", datetime.now(UTC).isoformat())
    d.setdefault("updated_at", datetime.now(UTC).isoformat())
    d["onvif_events"] = bool(d.get("onvif_events", 0))
    d["enabled"] = bool(d.get("enabled", 1))
    return d


@router.get("", response_model=list[CameraOut])
async def list_cameras(request: Request, _: Auth):
    recorder = request.app.state.recorder
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM cameras ORDER BY id") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["status"] = recorder.get_status(r["id"])
        _normalize(r)
    return [_normalize(r) for r in rows]


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
async def create_camera(payload: CameraCreate, request: Request, _: Auth):
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """INSERT INTO cameras
               (name, rtsp_url, substream_url, recording_mode, detection_mode,
                enabled, username, password, onvif_host, onvif_port, onvif_events)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                payload.name,
                payload.rtsp_url,
                payload.substream_url,
                payload.recording_mode.value,
                payload.detection_mode.value,
                int(payload.enabled),
                payload.username,
                payload.password,
                payload.onvif_host,
                payload.onvif_port,
                int(payload.onvif_events),
            ),
        )
        await db.commit()
        async with db.execute("SELECT * FROM cameras WHERE id=?", (cur.lastrowid,)) as c:
            row = dict(await c.fetchone())

    row = _normalize(row)
    if payload.enabled:
        await request.app.state.recorder.start_camera(row)
        row["status"] = "recording"
    return row


@router.get("/{camera_id}", response_model=CameraOut)
async def get_camera(camera_id: int, request: Request, _: Auth):
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    d = _normalize(dict(row))
    d["status"] = request.app.state.recorder.get_status(camera_id)
    return d


@router.patch("/{camera_id}", response_model=CameraOut)
async def update_camera(camera_id: int, payload: CameraUpdate, request: Request, _: Auth):
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Camera not found")

        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        for enum_field in ("recording_mode", "detection_mode"):
            if enum_field in updates and hasattr(updates[enum_field], "value"):
                updates[enum_field] = updates[enum_field].value
        if "enabled" in updates:
            updates["enabled"] = int(updates["enabled"])
        if "onvif_events" in updates:
            updates["onvif_events"] = int(updates["onvif_events"])

        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [camera_id]
            await db.execute(
                f"UPDATE cameras SET {set_clause}, updated_at=datetime('now') WHERE id=?", values
            )
            await db.commit()

        async with db.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)) as cur:
            updated = _normalize(dict(await cur.fetchone()))

    recorder = request.app.state.recorder
    await recorder.stop_camera(camera_id)
    if updated.get("enabled"):
        await recorder.start_camera(updated)
        updated["status"] = "recording"
    else:
        updated["status"] = "stopped"
    return updated


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int, request: Request, _: Auth):
    await request.app.state.recorder.stop_camera(camera_id)
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
        await db.commit()
