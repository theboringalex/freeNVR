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

    # ONVIF
    ONVIF_PULL_INTERVAL: float = float(os.getenv("ONVIF_PULL_INTERVAL", "2.0"))
    ONVIF_TIMEOUT: int = int(os.getenv("ONVIF_TIMEOUT", "10"))

    # Coral / AI Detection
    CORAL_MODEL_PATH: str = os.getenv(
        "CORAL_MODEL_PATH",
        "models/ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite",
    )
    CORAL_LABELS_PATH: str = os.getenv("CORAL_LABELS_PATH", "models/coco_labels.txt")
    CORAL_SCORE_THRESHOLD: float = float(os.getenv("CORAL_SCORE_THRESHOLD", "0.5"))
    CORAL_INFERENCE_FPS: float = float(os.getenv("CORAL_INFERENCE_FPS", "1.0"))
    CORAL_DETECT_CLASSES: list[str] = os.getenv(
        "CORAL_DETECT_CLASSES", "person,car,truck,bus,motorcycle,dog,cat"
    ).split(",")


settings = Settings()
