import asyncio
import logging
import os
import signal
from datetime import datetime, UTC
from pathlib import Path

import aiosqlite

from app.config import settings

logger = logging.getLogger(__name__)


class CameraRecorder:
    def __init__(self, camera: dict):
        self.camera = camera
        self.process: asyncio.subprocess.Process | None = None
        self.running = False
        self._task: asyncio.Task | None = None

    @property
    def camera_id(self) -> int:
        return self.camera["id"]

    def _build_rtsp_url(self) -> str:
        url = self.camera["rtsp_url"]
        user = self.camera.get("username")
        pwd = self.camera.get("password")
        if user and pwd and "://" in url:
            scheme, rest = url.split("://", 1)
            return f"{scheme}://{user}:{pwd}@{rest}"
        return url

    def _segment_path(self) -> Path:
        now = datetime.now(UTC)
        base = settings.RECORDINGS_PATH / str(self.camera_id) / now.strftime("%Y/%m/%d")
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _ffmpeg_cmd(self) -> list[str]:
        rtsp_url = self._build_rtsp_url()
        out_dir = self._segment_path()
        segment_file = str(out_dir / "%Y%m%d_%H%M%S.mp4")

        return [
            settings.FFMPEG_BIN,
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", "segment",
            "-segment_time", str(settings.SEGMENT_DURATION),
            "-segment_atclocktime", "1",
            "-reset_timestamps", "1",
            "-strftime", "1",
            "-segment_format", "mp4",
            "-movflags", "+faststart",
            segment_file,
        ]

    def _hls_cmd(self) -> list[str]:
        rtsp_url = self._build_rtsp_url()
        hls_dir = settings.HLS_PATH / str(self.camera_id)
        hls_dir.mkdir(parents=True, exist_ok=True)
        playlist = str(hls_dir / "live.m3u8")

        return [
            settings.FFMPEG_BIN,
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-c:a", "aac",
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", str(settings.HLS_LIST_SIZE),
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", str(hls_dir / "seg%03d.ts"),
            playlist,
        ]

    async def _run_recording(self):
        while self.running:
            cmd = self._ffmpeg_cmd()
            logger.info("Starting recording for camera %d: %s", self.camera_id, self.camera["name"])
            try:
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                start_time = datetime.now(UTC)
                recording_id = await self._insert_recording(start_time)

                _, stderr = await self.process.communicate()
                end_time = datetime.now(UTC)

                if stderr:
                    last_lines = stderr.decode(errors="replace").strip().split("\n")[-3:]
                    for line in last_lines:
                        if line.strip():
                            logger.debug("ffmpeg [cam %d]: %s", self.camera_id, line)

                await self._finalize_recording(recording_id, end_time)
                await self._update_status("recording")

            except Exception as e:
                logger.error("Recorder error for camera %d: %s", self.camera_id, e)
                await self._update_status("error")

            if self.running:
                await asyncio.sleep(2)

    async def _insert_recording(self, start_time: datetime) -> int:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            now_str = start_time.isoformat()
            cursor = await db.execute(
                "INSERT INTO recordings (camera_id, file_path, start_time, size_bytes) VALUES (?, ?, ?, 0)",
                (self.camera_id, "", now_str),
            )
            await db.commit()
            return cursor.lastrowid

    async def _finalize_recording(self, recording_id: int, end_time: datetime):
        out_dir = self._segment_path()
        total_size = sum(f.stat().st_size for f in out_dir.glob("*.mp4") if f.is_file())
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(
                "UPDATE recordings SET end_time=?, size_bytes=? WHERE id=?",
                (end_time.isoformat(), total_size, recording_id),
            )
            await db.commit()

    async def _update_status(self, status: str):
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(
                "UPDATE cameras SET status=?, updated_at=datetime('now') WHERE id=?",
                (status, self.camera_id),
            )
            await db.commit()

    async def start(self):
        if self.camera["recording_mode"] == "disabled":
            return
        self.running = True
        self._task = asyncio.create_task(self._run_recording())
        await self._update_status("recording")

    async def stop(self):
        self.running = False
        if self.process and self.process.returncode is None:
            try:
                self.process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._update_status("stopped")


class RecorderManager:
    def __init__(self):
        self._recorders: dict[int, CameraRecorder] = {}

    async def start_all(self):
        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM cameras WHERE enabled=1") as cursor:
                cameras = [dict(row) async for row in cursor]

        for cam in cameras:
            await self.start_camera(cam)

    async def start_camera(self, camera: dict):
        cam_id = camera["id"]
        if cam_id in self._recorders:
            await self._recorders[cam_id].stop()
        recorder = CameraRecorder(camera)
        self._recorders[cam_id] = recorder
        await recorder.start()

    async def stop_camera(self, camera_id: int):
        if camera_id in self._recorders:
            await self._recorders[camera_id].stop()
            del self._recorders[camera_id]

    async def stop_all(self):
        tasks = [r.stop() for r in self._recorders.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._recorders.clear()

    def get_status(self, camera_id: int) -> str:
        if camera_id in self._recorders:
            r = self._recorders[camera_id]
            return "recording" if r.running else "stopped"
        return "stopped"
