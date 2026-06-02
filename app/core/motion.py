"""
Simple motion detection via FFmpeg's scene change filter.
Runs as a lightweight subprocess that reads the RTSP stream and emits
motion events when scene change score exceeds the threshold.
"""
import asyncio
import logging
import re
from datetime import datetime, UTC

import aiosqlite

from app.config import settings

logger = logging.getLogger(__name__)
_SCORE_RE = re.compile(r"lavfi\.scene_score=([0-9.]+)")


class MotionDetector:
    def __init__(self, camera_id: int, rtsp_url: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._task: asyncio.Task | None = None
        self.running = False
        self._cooldown = 10  # seconds between events

    def _cmd(self) -> list[str]:
        return [
            settings.FFMPEG_BIN,
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-vf", f"select='gt(scene,{settings.MOTION_THRESHOLD})',showinfo",
            "-f", "null",
            "-",
        ]

    async def _detect(self):
        last_event = 0.0
        while self.running:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *self._cmd(),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                async for line in proc.stderr:
                    if not self.running:
                        break
                    decoded = line.decode(errors="replace")
                    m = _SCORE_RE.search(decoded)
                    if m:
                        score = float(m.group(1))
                        now = asyncio.get_event_loop().time()
                        if score > settings.MOTION_THRESHOLD and (now - last_event) > self._cooldown:
                            last_event = now
                            await self._emit_event()
                proc.terminate()
            except Exception as e:
                logger.debug("Motion detector error cam %d: %s", self.camera_id, e)
            if self.running:
                await asyncio.sleep(5)

    async def _emit_event(self):
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(
                "INSERT INTO events (camera_id, event_type, timestamp) VALUES (?, 'motion', ?)",
                (self.camera_id, datetime.now(UTC).isoformat()),
            )
            await db.commit()
        logger.info("Motion detected on camera %d", self.camera_id)

    def start(self):
        if not settings.MOTION_ENABLED:
            return
        self.running = True
        self._task = asyncio.create_task(self._detect())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
