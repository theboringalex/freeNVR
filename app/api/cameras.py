from datetime import datetime, UTC
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.core.auth import require_api_key
from app.core.database import get_db
from app.models import CameraCreate, CameraOut, CameraUpdate

router = APIRouter()
Auth = Annotated[str, Depends(require_api_key)]


def _row_to_camera(row) -> dict:
    d = dict(row)
    d["status"] = d.get("status", "stopped")
    d.setdefault("created_at", datetime.now(UTC).isoformat())
    d.setdefault("updated_at", datetime.now(UTC).isoformat())
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
        r.setdefault("created_at", datetime.now(UTC).isoformat())
        r.setdefault("updated_at", datetime.now(UTC).isoformat())
    return rows


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
async def create_camera(payload: CameraCreate, request: Request, _: Auth):
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """INSERT INTO cameras
               (name, rtsp_url, substream_url, recording_mode, enabled, username, password)
               VALUES (?,?,?,?,?,?,?)""",
            (
                payload.name,
                payload.rtsp_url,
                payload.substream_url,
                payload.recording_mode.value,
                int(payload.enabled),
                payload.username,
                payload.password,
            ),
        )
        await db.commit()
        cam_id = cur.lastrowid
        async with db.execute("SELECT * FROM cameras WHERE id=?", (cam_id,)) as c:
            row = dict(await c.fetchone())

    row["status"] = "stopped"
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
    d = dict(row)
    d["status"] = request.app.state.recorder.get_status(camera_id)
    d.setdefault("created_at", datetime.now(UTC).isoformat())
    d.setdefault("updated_at", datetime.now(UTC).isoformat())
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
        if "recording_mode" in updates:
            updates["recording_mode"] = updates["recording_mode"].value
        if "enabled" in updates:
            updates["enabled"] = int(updates["enabled"])

        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [camera_id]
            await db.execute(
                f"UPDATE cameras SET {set_clause}, updated_at=datetime('now') WHERE id=?", values
            )
            await db.commit()

        async with db.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)) as cur:
            updated = dict(await cur.fetchone())

    recorder = request.app.state.recorder
    await recorder.stop_camera(camera_id)
    if updated.get("enabled"):
        await recorder.start_camera(updated)
        updated["status"] = "recording"
    else:
        updated["status"] = "stopped"

    updated.setdefault("created_at", datetime.now(UTC).isoformat())
    updated.setdefault("updated_at", datetime.now(UTC).isoformat())
    return updated


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int, request: Request, _: Auth):
    await request.app.state.recorder.stop_camera(camera_id)
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
        await db.commit()
