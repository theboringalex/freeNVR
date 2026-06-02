from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class RecordingMode(str, Enum):
    CONTINUOUS = "continuous"
    MOTION = "motion"
    DISABLED = "disabled"


class DetectionMode(str, Enum):
    NONE = "none"
    FFMPEG = "ffmpeg"
    CORAL = "coral"


class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    substream_url: Optional[str] = None
    recording_mode: RecordingMode = RecordingMode.CONTINUOUS
    detection_mode: DetectionMode = DetectionMode.FFMPEG
    enabled: bool = True
    username: Optional[str] = None
    password: Optional[str] = None
    # ONVIF
    onvif_host: Optional[str] = None
    onvif_port: int = 8000
    onvif_events: bool = False


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    substream_url: Optional[str] = None
    recording_mode: Optional[RecordingMode] = None
    detection_mode: Optional[DetectionMode] = None
    enabled: Optional[bool] = None
    username: Optional[str] = None
    password: Optional[str] = None
    onvif_host: Optional[str] = None
    onvif_port: Optional[int] = None
    onvif_events: Optional[bool] = None


class CameraOut(BaseModel):
    id: int
    name: str
    rtsp_url: str
    substream_url: Optional[str]
    recording_mode: RecordingMode
    detection_mode: DetectionMode
    enabled: bool
    username: Optional[str]
    status: str
    onvif_host: Optional[str]
    onvif_port: int
    onvif_events: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecordingOut(BaseModel):
    id: int
    camera_id: int
    camera_name: str
    file_path: str
    start_time: datetime
    end_time: Optional[datetime]
    size_bytes: int
    has_motion: bool

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    camera_id: int
    camera_name: str
    event_type: str
    timestamp: datetime
    thumbnail_path: Optional[str]
    recording_id: Optional[int]

    class Config:
        from_attributes = True


class StorageInfo(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    recording_count: int


class ONVIFDiscoverResult(BaseModel):
    address: str
    name: Optional[str]
    hardware: Optional[str]
    location: Optional[str]
    rtsp_url: Optional[str]


class ONVIFImportPayload(BaseModel):
    onvif_host: str
    onvif_port: int = 8000
    username: str
    password: str
    camera_name: Optional[str] = None
    recording_mode: RecordingMode = RecordingMode.CONTINUOUS
    detection_mode: DetectionMode = DetectionMode.FFMPEG
    onvif_events: bool = True
