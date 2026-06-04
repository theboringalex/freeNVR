"""freeNVR Camera entities for Home Assistant."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    cameras = [
        FreeNVRCamera(coordinator, cam, data["base_url"], data["api_key"], data["session"])
        for cam in coordinator.data.get("cameras", [])
    ]
    async_add_entities(cameras, True)


class FreeNVRCamera(CoordinatorEntity, Camera):
    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, cam_data: dict, base_url: str, api_key: str, session):
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._cam = cam_data
        self._base_url = base_url
        self._api_key = api_key
        self._session = session
        self._attr_unique_id = f"freenvr_camera_{cam_data['id']}"
        self._attr_name = cam_data["name"]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._cam["id"]))},
            name=self._cam["name"],
            manufacturer="freeNVR",
            model="IP Camera",
        )

    @property
    def is_recording(self) -> bool:
        cam = self._current_cam()
        return cam.get("status") == "recording" if cam else False

    @property
    def motion_detection_enabled(self) -> bool:
        cam = self._current_cam()
        return cam.get("recording_mode") == "motion" if cam else False

    @property
    def extra_state_attributes(self) -> dict:
        cam = self._current_cam() or self._cam
        return {
            "camera_id": cam.get("id"),
            "recording_mode": cam.get("recording_mode"),
            "status": cam.get("status"),
            "rtsp_url": cam.get("rtsp_url"),
        }

    def _current_cam(self) -> dict | None:
        if not self.coordinator.data:
            return None
        for c in self.coordinator.data.get("cameras", []):
            if c["id"] == self._cam["id"]:
                return c
        return None

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        url = f"{self._base_url}/streams/{self._cam['id']}/snapshot"
        try:
            async with self._session.get(
                url,
                headers={"X-API-Key": self._api_key},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
        except aiohttp.ClientError as err:
            _LOGGER.warning("Snapshot failed for camera %s: %s", self._cam["name"], err)
        return None

    async def stream_source(self) -> str | None:
        cam = self._current_cam() or self._cam
        return cam.get("rtsp_url")
