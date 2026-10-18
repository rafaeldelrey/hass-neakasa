"""Sensor for the timestamp of the last cat usage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..coordinator import NeakasaCoordinator, NeakasaDeviceSnapshot

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceInfo

# Records kept in the `recent_visits` attribute, newest first. About 110 bytes each, so
# 100 stay well under the recorder's 16 KiB limit for an entity's attributes.
MAX_RECENT_VISITS = 100


class NeakasaLastUsageSensor(CoordinatorEntity[NeakasaCoordinator], SensorEntity):
    """Timestamp of the last time a cat used the litter box."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "last_usage"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: NeakasaCoordinator,
        device_info: DeviceInfo,
        iot_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._iot_id = iot_id
        self.device_info = device_info
        self._attr_unique_id = f"{iot_id}-last_usage"

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update entity state from coordinator data."""
        if self.entity_id is None:
            return
        self._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Write initial state once entity_id is assigned."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    @property
    def _snap(self) -> NeakasaDeviceSnapshot | None:
        return self.coordinator.device_snapshot(self._iot_id)

    @property
    def native_value(self) -> datetime | None:
        """Return the last-use timestamp."""
        snap = self._snap
        if snap is None:
            return None
        raw = snap.last_use
        if not raw:
            return None
        try:
            return datetime.fromtimestamp(raw / 1000, tz=UTC)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """
        Return the box's recent visits, including those no cat was identified for.

        Each visit has its start and end (ISO 8601, UTC), the measured weight in kg and
        the identified cat's name, or None when the box matched no cat profile. The cat
        weight sensors only expose identified visits, one per cat.
        """
        snap = self._snap
        if snap is None:
            return {}
        names = {str(cat.get("id")): cat.get("name") for cat in snap.cat_list}
        visits: list[dict[str, Any]] = []
        for record in snap.record_list[:MAX_RECENT_VISITS]:
            start = record.get("start_time")
            end = record.get("end_time")
            if not isinstance(start, int | float) or not isinstance(end, int | float):
                continue
            visits.append(
                {
                    "start": datetime.fromtimestamp(start, tz=UTC).isoformat(),
                    "end": datetime.fromtimestamp(end, tz=UTC).isoformat(),
                    "weight_kg": record.get("weight"),
                    "cat": names.get(str(record.get("cat_id"))),
                }
            )
        return {"recent_visits": visits}
