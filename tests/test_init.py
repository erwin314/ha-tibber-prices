"""Test initialization of tibber_prices."""
from unittest.mock import patch, AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tibber_prices.const import DOMAIN, CONF_ACCESS_TOKEN

async def test_setup_and_unload_entry(hass):
    """Test setting up and unloading the integration."""
    # 1. Create a mock config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCESS_TOKEN: "test_token_123"},
        entry_id="test_entry_id"
    )
    entry.add_to_hass(hass)

    # 2. Mock the external API call
    # We mock _fetch_data to prevent actual network calls.
    # We use AsyncMock because _fetch_data is an async method.
    with patch(
        "custom_components.tibber_prices.coordinator.TibberDataCoordinator._fetch_data",
        new_callable=AsyncMock
    ) as mock_fetch:

        # 3. Test setup
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Verify the integration was successfully loaded into HA
        assert DOMAIN in hass.data
        assert entry.entry_id in hass.data[DOMAIN]

        # Verify the fetch was attempted (since cache is empty)
        mock_fetch.assert_called_once()

        # 4. Test unload
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        # Verify it cleaned up properly
        assert entry.entry_id not in hass.data[DOMAIN]
