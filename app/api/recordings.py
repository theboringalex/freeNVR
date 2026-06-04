from datetime import datetime
from typing import Optional
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Annotated

from app.config import settings
from app.core.auth import require_api_key

router = APIRouter()
Auth = Annotated[str, Depends(require_api_key)]


@router.get("")
async def list_recordings(
    _: Auth,
    camera_id: Optional[int] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    conditions = []
    params: list = []

    if camera_id is not None:
        conditions.append("r.camera_id=?")
        params.append(camera_id)
    if start:
        conditions.append("r.start_time>=?")
        params.append(start)
    if end:
        conditions.append("r.start_time<=?")
        params.append(end)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = f"""
            SELECT r.*, c.name as camera_name
            FROM recordings r
            JOIN cameras c ON c.id = r.camera_id
            {where}
            ORDER BY r.start_time DESC
            LIMIT ? OFFSET ?
        """
        async with db.execute(query, params) as cur:
            return [dict(row) for row in await cur.fetchall()]


@router.get("/{recording_id}/download")
async def download_recording(recording_id: int, _: Auth):
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Find actual file
    cam_id = row["camera_id"]
    start = datetime.fromisoformat(row["start_time"])
    search_dir = settings.RECORDINGS_PATH / str(cam_id) / start.strftime("%Y/%m/%d")

    if not search_dir.exists():
        raise HTTPException(status_code=404, detail="Recording file not found")

    files = sorted(search_dir.glob("*.mp4"))
    if not files:
        raise HTTPException(status_code=404, detail="No recording files found")

    return FileResponse(
        path=files[0],
        media_type="video/mp4",
        filename=f"recording_{recording_id}_{start.strftime('%Y%m%d_%H%M%S')}.mp4",
    )


@router.get("/storage/info")
async def storage_info(_: Auth):
    import shutil

    total, used, free = shutil.disk_usage(str(settings.RECORDINGS_PATH.parent))

    async with aiosqlite.connect(settings.DB_PATH) as db:
        async with db.execute("SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM recordings") as cur:
            count, rec_size = await cur.fetchone()

    return {
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "recording_count": count,
        "recording_size_bytes": rec_size,
    }


@router.delete("/{recording_id}", status_code=204)
async def delete_recording(recording_id: int, _: Auth):
    async with aiosqlite.connect(settings.DB_PATH) as db:
        async with db.execute("SELECT camera_id, start_time FROM recordings WHERE id=?", (recording_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recording not found")
        await db.execute("DELETE FROM recordings WHERE id=?", (recording_id,))
        await db.commit()
