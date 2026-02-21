"""API client for Tibber."""

from typing import Any

import aiohttp

from .const import API_URL


class TibberAuthError(Exception):
    """Exception raised when authentication fails."""


class TibberConnectionError(Exception):
    """Exception raised when connection fails."""


class TibberDataError(Exception):
    """Exception raised when data is missing or invalid."""


async def _execute_query(
    session: aiohttp.ClientSession,
    token: str,
    query: str,
    variables: dict | None = None,
) -> dict[str, Any]:
    """Execute a GraphQL query against the Tibber API."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        async with session.post(API_URL, json=payload, headers=headers) as response:
            if response.status == 401:
                raise TibberAuthError("Authentication failed")
            if response.status != 200:
                raise TibberConnectionError(f"API returned status {response.status}")

            try:
                json_data = await response.json()
            except aiohttp.ContentTypeError as err:
                raise TibberConnectionError("Failed to parse JSON response") from err

            if "error" in json_data:
                msg = str(json_data["error"]).lower()
                if (
                    "no access token" in msg
                    or "invalid token" in msg
                    or "unauthorized" in msg
                ):
                    raise TibberAuthError(str(json_data["error"]))
                raise TibberConnectionError(f"API error: {json_data['error']}")

            if "errors" in json_data:
                for error in json_data["errors"]:
                    msg = error.get("message", "").lower()
                    code = error.get("extensions", {}).get("code", "")
                    if (
                        "unauthorized" in msg
                        or "invalid token" in msg
                        or code == "UNAUTHENTICATED"
                    ):
                        raise TibberAuthError(
                            error.get("message", "Authentication failed")
                        )
                raise TibberConnectionError(f"API errors: {json_data['errors']}")

            return json_data

    except aiohttp.ClientError as err:
        raise TibberConnectionError(f"Network error: {err}") from err


async def get_homes(session: aiohttp.ClientSession, token: str) -> list[dict[str, Any]]:
    """Fetch available homes from Tibber."""
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

    json_data = await _execute_query(session, token, query)

    data = json_data.get("data", {}).get("viewer", {}).get("homes", [])
    if not data:
        raise TibberDataError("No homes found")

    homes = []
    for home in data:
        name = (
            home.get("appNickname")
            or home.get("address", {}).get("address1")
            or "Tibber Home"
        )
        homes.append({"id": home["id"], "name": name})

    return homes


async def get_prices(
    session: aiohttp.ClientSession, token: str, home_id: str
) -> tuple[dict, str | None]:
    """Fetch price info from Tibber."""
    query = """
    query($homeId: ID!) {
      viewer {
        home(id: $homeId) {
          currentSubscription {
            priceInfo(resolution: QUARTER_HOURLY) {
              current {
                currency
              }
              today {
                total
                startsAt
              }
              tomorrow {
                total
                startsAt
              }
            }
          }
        }
      }
    }
    """

    json_data = await _execute_query(session, token, query, {"homeId": home_id})

    data = json_data.get("data", {}).get("viewer", {}).get("home", {})
    if not data:
        raise TibberDataError("Home not found")

    price_info = data.get("currentSubscription", {}).get("priceInfo", {})
    if not price_info:
        raise TibberDataError("No price info found (active subscription?)")

    current_info = price_info.get("current")
    currency = current_info.get("currency") if current_info else None

    new_data = {}
    for day_key in ["today", "tomorrow"]:
        points = price_info.get(day_key, [])
        for point in points:
            start_at = point["startsAt"]
            total = point["total"]
            new_data[start_at] = total

    if not new_data:
        raise TibberDataError("No price data returned from API")

    return new_data, currency
