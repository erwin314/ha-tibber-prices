"""Config flow for Tibber Prices integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .const import API_URL, CONF_ACCESS_TOKEN, CONF_HOME_ID, CONF_HOME_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
    }
)


async def validate_input(hass: HomeAssistant, token: str) -> list[dict[str, Any]]:
    """Validate the user input allows us to connect and fetch homes."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Query to fetch available homes
    query = """
    {
      viewer {
        homes {
          id
          appNickname
          address {
            address1
          }
        }
      }
    }
    """

    session = aiohttp_client.async_get_clientsession(hass)
    try:
        async with session.post(
            API_URL, json={"query": query}, headers=headers
        ) as response:
            if response.status == 401:
                raise InvalidAuth
            if response.status != 200:
                raise CannotConnect(f"Status not 200: {response.status}")

            json_data = await response.json()
            if "errors" in json_data:
                # Check for unauthorized in errors
                for error in json_data["errors"]:
                    if (
                        "message" in error
                        and "unauthorized" in error["message"].lower()
                    ):
                        raise InvalidAuth
                raise CannotConnect(f"API Errors: {json_data['errors']}")

            data = json_data.get("data", {}).get("viewer", {}).get("homes", [])
            if not data:
                raise NoHomesFound

            homes = []
            for home in data:
                name = (
                    home.get("appNickname")
                    or home.get("address", {}).get("address1")
                    or "Tibber Home"
                )
                homes.append({"id": home["id"], "name": name})

            return homes

    except aiohttp.ClientError:
        raise CannotConnect
    except (InvalidAuth, NoHomesFound):
        raise
    except Exception as err:
        _LOGGER.exception("Unexpected exception during validation")
        raise CannotConnect from err


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
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoHomesFound:
                errors["base"] = "no_homes_found"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if len(self.homes) == 1:
                    return await self._create_tibber_entry(self.homes[0])
                return await self.async_step_home()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
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

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauth dialog."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN]
            try:
                # Validate the new token
                homes = await validate_input(self.hass, token)

                # Verify the existing home is still available with this token
                # We need to find the entry that triggered reauth
                reauth_entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                if reauth_entry:
                    home_id = reauth_entry.data[CONF_HOME_ID]
                    if not any(h["id"] == home_id for h in homes):
                        errors["base"] = "home_not_found_with_token"
                    else:
                        self.hass.config_entries.async_update_entry(
                            reauth_entry,
                            data={**reauth_entry.data, CONF_ACCESS_TOKEN: token},
                        )
                        await self.hass.config_entries.async_reload(
                            reauth_entry.entry_id
                        )
                        return self.async_abort(reason="reauth_successful")

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-configuration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN]
            try:
                homes = await validate_input(self.hass, token)
                # Verify the current home is in legitimate list
                current_home_id = entry.data[CONF_HOME_ID]
                if not any(h["id"] == current_home_id for h in homes):
                    errors["base"] = "home_not_found_with_token"
                else:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_ACCESS_TOKEN: token}
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACCESS_TOKEN, default=entry.data.get(CONF_ACCESS_TOKEN)
                    ): str
                }
            ),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class NoHomesFound(HomeAssistantError):
    """Error to indicate no homes found on account."""
