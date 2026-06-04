"""freeNVR binary sensors (motion detection) for Home Assistant."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
MOTION_WINDOW = timedelta(minutes=1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    sensors = [
        FreeNVRMotionSensor(coordinator, cam)
        for cam in coordinator.data.get("cameras", [])
    ]
    async_add_entities(sensors, True)


class FreeNVRMotionSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator, cam_data: dict):
        super().__init__(coordinator)
        self._cam = cam_data
        self._attr_unique_id = f"freenvr_motion_{cam_data['id']}"
        self._attr_name = f"{cam_data['name']} Bewegung"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, str(self._cam["id"]))})

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        events = self.coordinator.data.get("events", [])
        now = datetime.now(timezone.utc)
        for evt in events:
            if evt.get("camera_id") != self._cam["id"]:
                continue
            if evt.get("event_type") != "motion":
                continue
            try:
                ts = datetime.fromisoformat(evt["timestamp"].replace("Z", "+00:00"))
                if (now - ts) < MOTION_WINDOW:
                    return True
            except (ValueError, KeyError):
                pass
        return False
