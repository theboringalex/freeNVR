import os
from pathlib import Path


class Settings:
    APP_HOST: str = os.getenv("FREENVR_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("FREENVR_PORT", "8765"))
    API_KEY: str = os.getenv("FREENVR_API_KEY", "changeme")

    RECORDINGS_PATH: Path = Path(os.getenv("RECORDINGS_PATH", "recordings"))
    HLS_PATH: Path = Path(os.getenv("HLS_PATH", "recordings/hls"))
    DB_PATH: str = os.getenv("DB_PATH", "config/freenvr.db")

    SEGMENT_DURATION: int = int(os.getenv("SEGMENT_DURATION", "60"))
    HLS_LIST_SIZE: int = int(os.getenv("HLS_LIST_SIZE", "5"))

    FFMPEG_BIN: str = os.getenv("FFMPEG_BIN", "ffmpeg")
    FFPROBE_BIN: str = os.getenv("FFPROBE_BIN", "ffprobe")

    MOTION_ENABLED: bool = os.getenv("MOTION_ENABLED", "true").lower() == "true"
    MOTION_THRESHOLD: float = float(os.getenv("MOTION_THRESHOLD", "0.02"))


settings = Settings()
