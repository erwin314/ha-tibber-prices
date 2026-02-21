"""Config flow for Tibber Prices integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .api import TibberAuthError, TibberConnectionError, TibberDataError, get_homes
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    DOMAIN,
    TIBBER_URL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
    }
)


async def validate_input(hass: HomeAssistant, token: str) -> list[dict[str, Any]]:
    """Validate the user input allows us to connect and fetch homes."""
    session = aiohttp_client.async_get_clientsession(hass)
    return await get_homes(session, token)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tibber Prices."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self.token: str | None = None
        self.homes: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self.token = user_input[CONF_ACCESS_TOKEN]
            try:
                self.homes = await validate_input(self.hass, self.token)
            except TibberConnectionError:
                errors["base"] = "cannot_connect"
            except TibberAuthError:
                errors["base"] = "invalid_auth"
            except TibberDataError:
                errors["base"] = "no_homes_found"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if len(self.homes) == 1:
                    return await self._create_tibber_entry(self.homes[0])
                return await self.async_step_home()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"tibber_url": TIBBER_URL},
        )

    async def async_step_home(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the home selection step."""
        if user_input is not None:
            home_id = user_input[CONF_HOME_ID]
            for home in self.homes:
                if home["id"] == home_id:
                    return await self._create_tibber_entry(home)

        # Generate list of homes for selection
        homes_dict = {home["id"]: home["name"] for home in self.homes}

        return self.async_show_form(
            step_id="home",
            data_schema=vol.Schema({vol.Required(CONF_HOME_ID): vol.In(homes_dict)}),
        )

    async def _create_tibber_entry(self, home: dict[str, Any]) -> FlowResult:
        """Create the config entry."""
        home_id = home["id"]

        # Abort if already configured
        unique_id = home_id
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=home["name"],
            data={
                CONF_ACCESS_TOKEN: self.token,
                CONF_HOME_ID: home_id,
                CONF_HOME_NAME: home["name"],
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication with a user."""
        self.token = entry_data[CONF_ACCESS_TOKEN]
        return await self.async_step_reauth_confirm()

    async def _handle_token_update(
        self, user_input: dict[str, Any] | None
    ) -> FlowResult:
        """Process token update for reauth and reconfigure flows."""
        errors: dict[str, str] = {}

        is_reconfigure = self.source == config_entries.SOURCE_RECONFIGURE

        if is_reconfigure:
            entry = self._get_reconfigure_entry()
            step_id = "reconfigure"
            data_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_ACCESS_TOKEN, default=entry.data.get(CONF_ACCESS_TOKEN)
                    ): str
                }
            )
        else:
            entry = self._get_reauth_entry()
            step_id = "reauth_confirm"
            # Note: do not set the old access token as default, because it is known to be invalid.
            data_schema = STEP_USER_DATA_SCHEMA

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN]
            try:
                homes = await validate_input(self.hass, token)
                if not any(h["id"] == entry.data[CONF_HOME_ID] for h in homes):
                    errors["base"] = "home_not_found_with_token"
                else:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_ACCESS_TOKEN: token}
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    abort_reason = (
                        "reconfigure_successful"
                        if is_reconfigure
                        else "reauth_successful"
                    )
                    return self.async_abort(reason=abort_reason)
            except TibberConnectionError:
                errors["base"] = "cannot_connect"
            except TibberAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauth dialog. (System initiated when handling ConfigEntryAuthFailed exception.)"""
        return await self._handle_token_update(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-configuration. (User-initiated when Reconfigure button is pressed.)"""
        return await self._handle_token_update(user_input)
