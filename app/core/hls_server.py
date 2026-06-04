import asyncio
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class HLSStreamer:
    """Manages per-camera HLS live streams using FFmpeg."""

    def __init__(self):
        self._processes: dict[int, asyncio.subprocess.Process] = {}

    def _hls_dir(self, camera_id: int) -> Path:
        d = settings.HLS_PATH / str(camera_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _cmd(self, camera_id: int, rtsp_url: str) -> list[str]:
        hls_dir = self._hls_dir(camera_id)
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
            str(hls_dir / "live.m3u8"),
        ]

    async def start(self, camera_id: int, rtsp_url: str):
        if camera_id in self._processes:
            return
        cmd = self._cmd(camera_id, rtsp_url)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._processes[camera_id] = proc
        logger.info("HLS stream started for camera %d", camera_id)

    async def stop(self, camera_id: int):
        proc = self._processes.pop(camera_id, None)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()

    def playlist_path(self, camera_id: int) -> Path:
        return self._hls_dir(camera_id) / "live.m3u8"

    def is_ready(self, camera_id: int) -> bool:
        return self.playlist_path(camera_id).exists()


hls_streamer = HLSStreamer()
