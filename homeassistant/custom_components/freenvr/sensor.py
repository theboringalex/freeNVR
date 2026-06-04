"""freeNVR sensors (storage, recording count) for Home Assistant."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        FreeNVRStorageSensor(data["coordinator"], data["base_url"], data["api_key"], data["session"]),
        FreeNVRRecordingCountSensor(data["coordinator"], data["base_url"], data["api_key"], data["session"]),
    ], True)


class _BaseStorageSensor(CoordinatorEntity, SensorEntity):
    _storage_data: dict | None = None

    def __init__(self, coordinator, base_url, api_key, session):
        super().__init__(coordinator)
        self._base_url = base_url
        self._api_key = api_key
        self._session = session

    async def async_update(self):
        try:
            async with self._session.get(
                f"{self._base_url}/recordings/storage/info",
                headers={"X-API-Key": self._api_key},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    self._storage_data = await resp.json()
        except aiohttp.ClientError:
            pass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "storage")},
            name="freeNVR Storage",
            manufacturer="freeNVR",
        )


class FreeNVRStorageSensor(_BaseStorageSensor):
    _attr_unique_id = "freenvr_storage_free"
    _attr_name = "freeNVR Freier Speicher"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES

    @property
    def native_value(self):
        if self._storage_data:
            return round(self._storage_data["free_bytes"] / 1e9, 2)
        return None


class FreeNVRRecordingCountSensor(_BaseStorageSensor):
    _attr_unique_id = "freenvr_recording_count"
    _attr_name = "freeNVR Aufnahmen"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "Aufnahmen"

    @property
    def native_value(self):
        if self._storage_data:
            return self._storage_data.get("recording_count", 0)
        return None
