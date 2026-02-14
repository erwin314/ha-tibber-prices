"""Sensor platform for Tibber Prices."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tibber Price sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensor = TibberPriceSensor(coordinator, entry)
    async_add_entities([sensor], True)

class TibberPriceSensor(SensorEntity):
    """Representation of a Tibber Price Sensor."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_price"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": DEFAULT_NAME,
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
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        # Update state every minute
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._update_state_by_timer, second=0
            )
        )

        self._update_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        self.async_write_ha_state()

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
