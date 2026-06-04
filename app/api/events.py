from typing import Optional, Annotated

import aiosqlite
from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.core.auth import require_api_key

router = APIRouter()
Auth = Annotated[str, Depends(require_api_key)]


@router.get("")
async def list_events(
    _: Auth,
    camera_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
):
    conditions = []
    params: list = []

    if camera_id is not None:
        conditions.append("e.camera_id=?")
        params.append(camera_id)
    if event_type:
        conditions.append("e.event_type=?")
        params.append(event_type)
    if start:
        conditions.append("e.timestamp>=?")
        params.append(start)
    if end:
        conditions.append("e.timestamp<=?")
        params.append(end)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = f"""
            SELECT e.*, c.name as camera_name
            FROM events e
            JOIN cameras c ON c.id = e.camera_id
            {where}
            ORDER BY e.timestamp DESC
            LIMIT ? OFFSET ?
        """
        async with db.execute(query, params) as cur:
            return [dict(row) for row in await cur.fetchall()]


@router.get("/latest")
async def latest_events(_: Auth, limit: int = Query(10, le=100)):
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT e.*, c.name as camera_name
               FROM events e
               JOIN cameras c ON c.id = e.camera_id
               ORDER BY e.timestamp DESC LIMIT ?""",
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
