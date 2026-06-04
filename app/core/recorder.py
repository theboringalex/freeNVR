import asyncio
import json
import logging
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
            if "@" not in rest:
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
                    for line in stderr.decode(errors="replace").strip().split("\n")[-3:]:
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
            cur = await db.execute(
                "INSERT INTO recordings (camera_id, file_path, start_time, size_bytes) VALUES (?, ?, ?, 0)",
                (self.camera_id, "", start_time.isoformat()),
            )
            await db.commit()
            return cur.lastrowid

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


# ─── RecorderManager ──────────────────────────────────────────────────────────

class RecorderManager:
    def __init__(self):
        self._recorders: dict[int, CameraRecorder] = {}
        self._onvif_subs: dict[int, object] = {}
        self._coral_detectors: dict[int, object] = {}
        self._motion_detectors: dict[int, object] = {}

    async def start_all(self):
        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM cameras WHERE enabled=1") as cur:
                cameras = [dict(row) async for row in cur]
        for cam in cameras:
            await self.start_camera(cam)

    async def start_camera(self, camera: dict):
        cam_id = camera["id"]
        await self.stop_camera(cam_id)

        # FFmpeg recorder (continuous or motion mode)
        if camera.get("recording_mode") != "disabled":
            recorder = CameraRecorder(camera)
            self._recorders[cam_id] = recorder
            await recorder.start()

        # FFmpeg motion detection (legacy / fallback)
        if camera.get("detection_mode", "ffmpeg") == "ffmpeg" and camera.get("recording_mode") == "motion":
            from app.core.motion import MotionDetector
            url = _rtsp_with_creds(camera)
            det = MotionDetector(cam_id, url)
            det.start()
            self._motion_detectors[cam_id] = det

        # ONVIF event subscription
        if camera.get("onvif_events"):
            from app.core.onvif_client import ONVIFEventSubscriber
            sub = ONVIFEventSubscriber(camera, self._on_event)
            sub.start()
            self._onvif_subs[cam_id] = sub

        # Coral / TFLite object detection
        if camera.get("detection_mode") == "coral":
            from app.core.coral_detector import CoralDetector
            det = CoralDetector(camera, self._on_coral_detection)
            det.start()
            self._coral_detectors[cam_id] = det

    async def stop_camera(self, camera_id: int):
        if camera_id in self._recorders:
            await self._recorders.pop(camera_id).stop()
        if camera_id in self._onvif_subs:
            await self._onvif_subs.pop(camera_id).stop()
        if camera_id in self._coral_detectors:
            await self._coral_detectors.pop(camera_id).stop()
        if camera_id in self._motion_detectors:
            await self._motion_detectors.pop(camera_id).stop()
            del self._motion_detectors[camera_id]

    async def stop_all(self):
        cams = list(self._recorders.keys())
        for cam_id in cams:
            await self.stop_camera(cam_id)

    def get_status(self, camera_id: int) -> str:
        r = self._recorders.get(camera_id)
        return "recording" if r and r.running else "stopped"

    async def _on_event(self, camera_id: int, source: str = "onvif", **kwargs):
        """Called when ONVIF motion event is received."""
        topic = kwargs.get("topic", "")
        metadata = json.dumps({"source": source, "topic": topic})
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(
                "INSERT INTO events (camera_id, event_type, timestamp, metadata) VALUES (?, 'motion', datetime('now'), ?)",
                (camera_id, metadata),
            )
            await db.commit()
        logger.info("Motion event cam %d [%s] topic=%s", camera_id, source, topic)

        # Trigger recording for motion-mode cameras
        recorder = self._recorders.get(camera_id)
        if recorder and not recorder.running:
            await recorder.start()

    async def _on_coral_detection(self, camera_id: int, detections: list[dict]):
        """Called when Coral/TFLite detects objects in a frame."""
        labels = [d["label"] for d in detections]
        metadata = json.dumps({"source": "coral", "detections": detections})
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(
                "INSERT INTO events (camera_id, event_type, timestamp, metadata) VALUES (?, ?, datetime('now'), ?)",
                (camera_id, ",".join(labels), metadata),
            )
            await db.commit()
        logger.info("Coral detection cam %d: %s", camera_id, labels)

        # Trigger recording
        recorder = self._recorders.get(camera_id)
        if recorder and not recorder.running:
            await recorder.start()


def _rtsp_with_creds(camera: dict) -> str:
    url = camera.get("rtsp_url", "")
    user = camera.get("username")
    pwd = camera.get("password")
    if user and pwd and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" not in rest:
            return f"{scheme}://{user}:{pwd}@{rest}"
    return url
