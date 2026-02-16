"""The Tibber Prices integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall


from .const import DOMAIN, CONF_ACCESS_TOKEN, CONF_HOME_ID
from .coordinator import TibberDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tibber Prices from a config entry."""

    token = entry.data.get(CONF_ACCESS_TOKEN)
    home_id = entry.data.get(CONF_HOME_ID)

    if not home_id:
        _LOGGER.error(
            "Tibber Prices configuration is missing 'home_id'. Please remove and re-add the integration."
        )
        return False

    coordinator = TibberDataCoordinator(hass, token, home_id)

    # Load cached data first
    await coordinator.async_load()

    # Perform first refresh (will raise ConfigEntryNotReady on failure or ConfigEntryAuthFailed)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    async def async_clear_cache_service(call: ServiceCall):
        """Clear cache for all entries."""
        # Iterate over all config entries for this domain
        for config_entry in hass.config_entries.async_entries(DOMAIN):
            if hasattr(config_entry, "runtime_data") and config_entry.runtime_data:
                coordinator = config_entry.runtime_data
                await coordinator.async_clear_cache()
                await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, "clear_cache"):
        hass.services.async_register(DOMAIN, "clear_cache", async_clear_cache_service)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Coordinator is stored in runtime_data, which HA handles.
        # We just need to ensure we don't need to manually cleanup anything else.
        pass

    return unload_ok
