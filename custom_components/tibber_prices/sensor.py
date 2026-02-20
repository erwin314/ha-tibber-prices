"""Sensor platform for Tibber Prices."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import TibberDataCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tibber Price sensor."""
    coordinator = entry.runtime_data
    sensor = TibberPriceSensor(coordinator, entry)
    async_add_entities([sensor], True)


class TibberPriceSensor(CoordinatorEntity[TibberDataCoordinator], SensorEntity):
    """Representation of a Tibber Price Sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "price"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator: TibberDataCoordinator, entry: ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_price"
        home_name = entry.data.get("home_name")
        device_name = f"Tibber {home_name}" if home_name else DEFAULT_NAME
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.unique_id)},
            "name": device_name,
            "manufacturer": "Tibber",
        }
        self._attr_native_value = None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        if self.coordinator.currency:
            return f"{self.coordinator.currency}/kWh"
        return None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        # Update state every 15 minutes (at the start of the quarter)
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._update_state_by_timer, minute=[0, 15, 30, 45], second=0
            )
        )
        self._update_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        super()._handle_coordinator_update()

    @callback
    def _update_state_by_timer(self, now) -> None:
        """Update state based on time."""
        self._update_state()
        self.async_write_ha_state()

    def _update_state(self):
        """Update the state of the sensor."""
        now = dt_util.now()
        price = self.coordinator.get_price_at(now)

        if price is not None:
            self._attr_native_value = price
            self._attr_available = True
        else:
            self._attr_native_value = None
            self._attr_available = False
