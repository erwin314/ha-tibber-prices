"""Coordinator for Tibber Prices."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
import random
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util import dt as dt_util

import aiohttp

from .const import DOMAIN, API_URL

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY_TEMPLATE = "{domain}.storage.{home_id}"
STORAGE_VERSION = 1
DAILY_UPDATE_HOUR_CET = 13  # Tibber publishes around 13:00 CET
UPDATE_INTERVAL = timedelta(minutes=60)  # check every hour


class TibberDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching and caching Tibber data."""

    def __init__(self, hass: HomeAssistant, access_token: str, home_id: str):
        """Initialize."""
        self.access_token = access_token
        self.home_id = home_id
        self._store = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY_TEMPLATE.format(domain=DOMAIN, home_id=home_id),
        )
        self.currency = None
        self._sorted_keys = []

        super().__init__(
            hass,
            _LOGGER,
            name=f"Tibber Prices {home_id}",
            update_interval=UPDATE_INTERVAL,
        )

    async def async_load(self):
        """Load data from cache."""
        try:
            stored = await self._store.async_load()
            if stored:
                if isinstance(stored, dict) and "data" in stored:
                    self.data = stored["data"]
                    self.currency = stored.get("currency")
                else:
                    # Legacy or simple format (just data dict)
                    self.data = stored
                    self.currency = None  # Unknown

                self._update_sorted_keys()
                _LOGGER.info("Loaded cached Tibber prices for home %s", self.home_id)
        except Exception:
            _LOGGER.exception("Failed to load cached data")

    async def _async_update_data(self):
        """Fetch data from API."""
        if self._has_sufficient_data():
            _LOGGER.debug("Sufficient data available, skipping fetch")
            self._schedule_next_interval()
            return self.data

        self.update_interval = timedelta(hours=1)  # Default retry interval
        try:
            new_data, currency = await self._fetch_data()

            self.data = new_data
            self.currency = currency
            self._update_sorted_keys()
            await self._save()
            self._schedule_next_interval()
            return self.data

        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _fetch_data(self):
        """Execute the API call."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

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

        variables = {"homeId": self.home_id}

        try:
            async with session.post(
                API_URL, json={"query": query, "variables": variables}, headers=headers
            ) as response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed("Authentication failed")
                if response.status != 200:
                    raise Exception(f"API returned status {response.status}")

                json_data = await response.json()
                if "errors" in json_data:
                    # Check for unauthorized in errors
                    for error in json_data["errors"]:
                        if (
                            "message" in error
                            and "unauthorized" in error["message"].lower()
                        ):
                            raise ConfigEntryAuthFailed(error["message"])
                    raise Exception(f"API errors: {json_data['errors']}")

                data = json_data.get("data", {}).get("viewer", {}).get("home", {})
                if not data:
                    raise Exception("Home not found")

                price_info = data.get("currentSubscription", {}).get("priceInfo", {})
                if not price_info:
                    # Maybe no subscription?
                    raise Exception("No price info found (active subscription?)")

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
                    # This might happen if API returns empty lists
                    raise Exception("No price data returned from API")

                return new_data, currency

        except aiohttp.ClientError as err:
            raise Exception(f"Network error: {err}") from err

    async def _save(self):
        """Save data to disk."""
        try:
            await self._store.async_save({"data": self.data, "currency": self.currency})
        except Exception:
            _LOGGER.exception("Error saving cache")

    def _has_sufficient_data(self):
        """Check if we have todays prices and tomorrow's prices (if it's after 13:00 CET)."""
        if not self.data:
            return False

        now = dt_util.now()
        has_today = False
        has_tomorrow = False

        for iso_ts in self.data:
            ts = dt_util.parse_datetime(iso_ts)
            if not ts:
                continue

            if ts.date() == now.date():
                has_today = True
            elif ts.date() == (now + timedelta(days=1)).date():
                has_tomorrow = True

        if not has_today:
            return False

        # If it's after the daily update time (13:00 CET), we should also have tomorrow's data
        now_cet = now.astimezone(ZoneInfo("Europe/Berlin"))
        if now_cet.hour >= DAILY_UPDATE_HOUR_CET and not has_tomorrow:
            return False

        return True

    def _update_sorted_keys(self):
        """Update sorted keys list."""
        valid_keys = []
        if self.data:
            for k in self.data:
                dt = dt_util.parse_datetime(k)
                if dt:
                    valid_keys.append((dt, k))
            valid_keys.sort(key=lambda x: x[0])
        self._sorted_keys = valid_keys

    def get_price_at(self, time_point: datetime):
        """Get price for a specific time."""
        if not self._sorted_keys:
            return None

        best_match_key = None
        best_match_dt = None

        for dt, key in self._sorted_keys:
            if dt <= time_point:
                best_match_key = key
                best_match_dt = dt
            else:
                break

        if best_match_key:
            if (time_point - best_match_dt) < timedelta(hours=1):
                return self.data[best_match_key]

        return None

    def _schedule_next_interval(self):
        """Schedule the next update interval smartly."""
        if self._has_sufficient_data():
            # We have sufficient data, so we can wait until the next publication time
            now = dt_util.now()
            now_cet = now.astimezone(ZoneInfo("Europe/Berlin"))

            # Target 13:05 CET (5 minutes later to optimize availability)
            target = now_cet.replace(
                hour=DAILY_UPDATE_HOUR_CET, minute=5, second=0, microsecond=0
            )

            # If we have sufficient data and it's past or at the update hour (13:00),
            # it means we already have tomorrow's prices. So schedule for the next day.
            # Also handle if we are before 13:05 but already have data (e.g. manual refresh at 13:02).
            if now_cet.hour >= DAILY_UPDATE_HOUR_CET or target <= now_cet:
                target += timedelta(days=1)

            # Add random jitter (0-10 minutes) in milliseconds to avoid thundering herd
            jitter_ms = random.randint(0, 10 * 60 * 1000)
            target += timedelta(milliseconds=jitter_ms)

            self.update_interval = target - now_cet
            _LOGGER.debug(
                "Data sufficient. Next update scheduled at %s (in %s)",
                target,
                self.update_interval,
            )
        else:
            # We are missing data (e.g. tomorrow's prices after 13:00), so check more frequently
            self.update_interval = timedelta(minutes=20)
            _LOGGER.debug("Data insufficient. Retrying in 20 minutes.")

    async def async_clear_cache(self):
        """Clear the cached data."""
        self.data = {}
        self.currency = None
        self._sorted_keys = []
        await self._store.async_remove()
        _LOGGER.info("Cleared cached Tibber prices")
        # Trigger update (will set data to None/empty or re-fetch?)
        # Standard DataUpdateCoordinator doesn't have a clear mechanism except modifying data
        self.async_set_updated_data({})
