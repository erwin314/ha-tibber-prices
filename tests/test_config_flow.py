"""Test the Tibber Prices config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tibber_prices.config_flow import (
    CannotConnect,
    InvalidAuth,
    NoHomesFound,
)
from custom_components.tibber_prices.const import (
    CONF_ACCESS_TOKEN,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    DOMAIN,
)


async def test_form(hass: HomeAssistant) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}


async def test_form_invalid_auth(hass: HomeAssistant) -> None:
    """Test we handle invalid auth."""
    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test_token"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect error."""
    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test_token"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_no_homes(hass: HomeAssistant) -> None:
    """Test we handle no homes found."""
    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        side_effect=NoHomesFound,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test_token"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "no_homes_found"}


async def test_flow_user_one_home(hass: HomeAssistant) -> None:
    """Test user flow with one home."""
    with (
        patch(
            "custom_components.tibber_prices.config_flow.validate_input",
            return_value=[{"id": "home1", "name": "My Home"}],
        ),
        patch("custom_components.tibber_prices.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test_token"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Home"
    assert result["data"] == {
        CONF_ACCESS_TOKEN: "test_token",
        CONF_HOME_ID: "home1",
        CONF_HOME_NAME: "My Home",
    }


async def test_flow_user_multiple_homes(hass: HomeAssistant) -> None:
    """Test user flow with multiple homes."""
    homes = [{"id": "home1", "name": "Home 1"}, {"id": "home2", "name": "Home 2"}]
    with (
        patch(
            "custom_components.tibber_prices.config_flow.validate_input",
            return_value=homes,
        ),
        patch("custom_components.tibber_prices.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test_token"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "home"

        # Select home 2
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOME_ID: "home2"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home 2"
    assert result["data"] == {
        CONF_ACCESS_TOKEN: "test_token",
        CONF_HOME_ID: "home2",
        CONF_HOME_NAME: "Home 2",
    }
