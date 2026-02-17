"""Tests for Tibber Data Coordinator."""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.tibber_prices.coordinator import TibberDataCoordinator


@pytest.fixture
def mock_coordinator(hass):
    """Create a mock coordinator."""
    return TibberDataCoordinator(hass, "test_token", "test_home_id")


async def test_sufficient_data_logic_early_day(mock_coordinator, hass):
    """Test standard fetch early in the day (before 14:00)."""
    # Mock time to 10:00 CET
    now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with patch("homeassistant.util.dt.now", return_value=now):
        # 1. Setup mock data: Today present, Tomorrow missing
        mock_coordinator.data = {"2023-10-27T00:00:00+02:00": 0.5}

        # Should be sufficient because it's before DAILY_UPDATE_HOUR_CET (13)
        assert mock_coordinator._has_sufficient_data() is True


async def test_sufficient_data_logic_late_day_missing_tomorrow(mock_coordinator, hass):
    """Test fetch late in the day (after 14:00) with missing tomorrow prices."""
    # Mock time to 16:00 CET
    now = datetime(2023, 10, 27, 16, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with patch("homeassistant.util.dt.now", return_value=now):
        # 1. Setup mock data: Today present, Tomorrow missing
        mock_coordinator.data = {"2023-10-27T00:00:00+02:00": 0.5}

        # Should be INSUFFICIENT because it's after 13:00 CET and tomorrow is missing
        # Note: Test mock time should be set such that it converts to >= 13:00 in CET
        assert mock_coordinator._has_sufficient_data() is False


async def test_sufficient_data_logic_late_day_with_tomorrow(mock_coordinator, hass):
    """Test fetch late in the day (after 14:00) with tomorrow prices present."""
    # Mock time to 16:00 CET
    now = datetime(2023, 10, 27, 16, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with patch("homeassistant.util.dt.now", return_value=now):
        # 1. Setup mock data: Today AND Tomorrow present
        mock_coordinator.data = {
            "2023-10-27T00:00:00+02:00": 0.5,
            "2023-10-28T00:00:00+02:00": 0.4,
        }

        # Should be sufficient
        assert mock_coordinator._has_sufficient_data() is True


async def test_update_data_uses_cache_if_sufficient(mock_coordinator, hass):
    """Test that _async_update_data uses cache if sufficient."""
    # Mock time to 10:00 CET
    now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with (
        patch("homeassistant.util.dt.now", return_value=now),
        patch.object(
            mock_coordinator, "_fetch_data", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        mock_coordinator.data = {"2023-10-27T00:00:00+02:00": 0.5}

        # Act
        data = await mock_coordinator._async_update_data()

        # Assert
        assert data == mock_coordinator.data
        mock_fetch.assert_not_called()


async def test_update_data_fetches_if_insufficient(mock_coordinator, hass):
    """Test that _async_update_data fetches if insufficient."""
    # Mock time to 16:00 CET
    now = datetime(2023, 10, 27, 16, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with (
        patch("homeassistant.util.dt.now", return_value=now),
        patch.object(
            mock_coordinator, "_fetch_data", new_callable=AsyncMock
        ) as mock_fetch,
        patch.object(mock_coordinator, "_save", new_callable=AsyncMock) as mock_save,
    ):
        mock_coordinator.data = {
            "2023-10-27T00:00:00+02:00": 0.5
        }  # Insufficient for 16:00

        new_data = {"2023-10-27T00:00:00+02:00": 0.5, "2023-10-28T00:00:00+02:00": 0.4}
        mock_fetch.return_value = (new_data, "NOK")

        # Act
        data = await mock_coordinator._async_update_data()

        # Assert
        assert data == new_data
        mock_fetch.assert_called_once()
        mock_save.assert_called_once()
        assert mock_coordinator.currency == "NOK"


async def test_update_data_raises_on_fetch_error(mock_coordinator, hass):
    """Test that _async_update_data raises UpdateFailed on fetch error."""
    with patch.object(
        mock_coordinator, "_fetch_data", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API Error")

        with pytest.raises(UpdateFailed):
            await mock_coordinator._async_update_data()
