from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class RecordingMode(str, Enum):
    CONTINUOUS = "continuous"
    MOTION = "motion"
    DISABLED = "disabled"


class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    substream_url: Optional[str] = None
    recording_mode: RecordingMode = RecordingMode.CONTINUOUS
    enabled: bool = True
    username: Optional[str] = None
    password: Optional[str] = None


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    substream_url: Optional[str] = None
    recording_mode: Optional[RecordingMode] = None
    enabled: Optional[bool] = None
    username: Optional[str] = None
    password: Optional[str] = None


class CameraOut(BaseModel):
    id: int
    name: str
    rtsp_url: str
    substream_url: Optional[str]
    recording_mode: RecordingMode
    enabled: bool
    username: Optional[str]
    status: str
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
