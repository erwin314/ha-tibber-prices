"""Config flow for Tibber Prices integration."""

import logging
from typing import Any

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN, API_URL, CONF_ACCESS_TOKEN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # Simple validation logic
    headers = {"Authorization": f"Bearer {data[CONF_ACCESS_TOKEN]}"}
    query = "{ viewer { login } }" # Minimal query to check validity

    session = aiohttp_client.async_get_clientsession(hass)
    try:
        async with session.post(API_URL, json={"query": query}, headers=headers) as response:
            if response.status != 200:
                raise InvalidAuth

            json_data = await response.json()
            if "errors" in json_data:
                raise InvalidAuth

            # If we get here, token is valid.
            return {"title": "Tibber Prices"}
    except Exception:
        raise CannotConnect

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tibber Prices."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
