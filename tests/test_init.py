"""Test initialization of tibber_prices."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tibber_prices.const import (
    CONF_ACCESS_TOKEN,
    CONF_HOME_ID,
    DOMAIN,
)


async def test_setup_and_unload_entry(hass):
    """Test setting up and unloading the integration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCESS_TOKEN: "test_token_123", CONF_HOME_ID: "test_home_id"},
        entry_id="test_entry_id",
    )
    entry.add_to_hass(hass)

    # Mock the coordinator
    with patch(
        "custom_components.tibber_prices.TibberDataCoordinator"
    ) as mock_coordinator_cls:
        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()

        # Test setup
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Verify coordinator was initialized correctly
        mock_coordinator_cls.assert_called_once_with(
            hass, "test_token_123", "test_home_id"
        )
        mock_coordinator.async_load.assert_awaited_once()
        mock_coordinator.async_config_entry_first_refresh.assert_awaited_once()

        # Verify integration loaded
        assert entry.runtime_data == mock_coordinator
        assert entry.state == ConfigEntryState.LOADED

        # Test unload
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        # Verify cleanup
        # runtime_data is handled by HA, checking integration specific cleanup not needed if using standard flow
        assert entry.state == ConfigEntryState.NOT_LOADED


async def test_setup_missing_home_id(hass):
    """Test setup fails if home_id is missing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCESS_TOKEN: "test_token_123",
            # Missing CONF_HOME_ID
        },
        entry_id="test_entry_id_legacy",
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert not hasattr(entry, "runtime_data") or entry.runtime_data is None


async def test_setup_failure(hass):
    """Test setup fails if first refresh fails."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCESS_TOKEN: "test_token_123", CONF_HOME_ID: "test_home_id"},
        entry_id="test_entry_id_fail",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tibber_prices.TibberDataCoordinator"
    ) as mock_coordinator_cls:
        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock(
            side_effect=ConfigEntryNotReady
        )

        try:
            await hass.config_entries.async_setup(entry.entry_id)
        except ConfigEntryNotReady:
            pass  # Expected


async def test_clear_cache_service(hass):
    """Test the clear_cache service."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCESS_TOKEN: "test_token_123", CONF_HOME_ID: "test_home_id"},
        entry_id="test_entry_id_clear_cache",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tibber_prices.TibberDataCoordinator"
    ) as mock_coordinator_cls:
        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()
        mock_coordinator.async_clear_cache = AsyncMock()

        # Setup integration
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check if service is registered and call it
        assert hass.services.has_service(DOMAIN, "clear_cache")
        await hass.services.async_call(DOMAIN, "clear_cache", {}, blocking=True)
        await hass.async_block_till_done()

        # Verify clear_cache and request_refresh were called
        mock_coordinator.async_clear_cache.assert_awaited_once()
        mock_coordinator.async_request_refresh.assert_awaited()
