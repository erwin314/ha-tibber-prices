"""Test the Tibber Prices config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tibber_prices.api import (
    TibberAuthError,
    TibberConnectionError,
    TibberDataError,
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
        side_effect=TibberAuthError,
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
        side_effect=TibberConnectionError,
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
        side_effect=TibberDataError,
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


async def test_form_unknown_error(hass: HomeAssistant) -> None:
    """Test we handle unknown errors."""
    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        side_effect=Exception("Unexpected exception"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test_token"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


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


async def test_reauth_flow(hass: HomeAssistant) -> None:
    """Test the reauthentication flow."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCESS_TOKEN: "old_token",
            CONF_HOME_ID: "home1",
            CONF_HOME_NAME: "My Home",
        },
        unique_id="home1",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
            "unique_id": mock_entry.unique_id,
        },
        data={"access_token": "old_token"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(
            "custom_components.tibber_prices.config_flow.validate_input",
            return_value=[{"id": "home1", "name": "My Home"}],
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_reload") as mock_reload,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "new_valid_token"},
        )
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "reauth_successful"
        assert mock_entry.data[CONF_ACCESS_TOKEN] == "new_valid_token"
        assert len(mock_reload.mock_calls) == 1


async def test_reauth_flow_home_not_found(hass: HomeAssistant) -> None:
    """Test reauth flow when the home is no longer available."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCESS_TOKEN: "old_token",
            CONF_HOME_ID: "home1",
            CONF_HOME_NAME: "My Home",
        },
        unique_id="home1",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
            "unique_id": mock_entry.unique_id,
        },
        data={"access_token": "old_token"},
    )

    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        return_value=[{"id": "different_home", "name": "Other Home"}],
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "new_valid_token"},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "reauth_confirm"
        assert result2["errors"] == {"base": "home_not_found_with_token"}


async def test_reauth_flow_exceptions(hass: HomeAssistant) -> None:
    """Test reauth flow handles network and auth exceptions."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCESS_TOKEN: "old_token",
            CONF_HOME_ID: "home1",
            CONF_HOME_NAME: "My Home",
        },
        unique_id="home1",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
            "unique_id": mock_entry.unique_id,
        },
        data={"access_token": "old_token"},
    )

    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        side_effect=TibberConnectionError,
    ):
        res_conn = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ACCESS_TOKEN: "new_token"}
        )
        assert res_conn["errors"] == {"base": "cannot_connect"}

    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        side_effect=TibberAuthError,
    ):
        res_auth = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ACCESS_TOKEN: "new_token"}
        )
        assert res_auth["errors"] == {"base": "invalid_auth"}

    with patch(
        "custom_components.tibber_prices.config_flow.validate_input",
        side_effect=Exception("Boom"),
    ):
        res_exc = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ACCESS_TOKEN: "new_token"}
        )
        assert res_exc["errors"] == {"base": "unknown"}


async def test_reconfigure_flow(hass: HomeAssistant) -> None:
    """Test the reconfiguration flow."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCESS_TOKEN: "old_token",
            CONF_HOME_ID: "home1",
            CONF_HOME_NAME: "My Home",
        },
        unique_id="home1",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    with (
        patch(
            "custom_components.tibber_prices.config_flow.validate_input",
            return_value=[{"id": "home1", "name": "My Home"}],
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_reload") as mock_reload,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "new_valid_token"},
        )
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"
        assert mock_entry.data[CONF_ACCESS_TOKEN] == "new_valid_token"
        assert len(mock_reload.mock_calls) == 1
