"""Coordinator for Tibber Prices."""

import logging
import asyncio
from datetime import datetime, timedelta
import random

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import DOMAIN, API_URL

_LOGGER = logging.getLogger(__name__)
STORAGE_KEY = f"{DOMAIN}.storage"
STORAGE_VERSION = 1

class TibberDataCoordinator:
    """Class to manage fetching and caching Tibber data."""

    def __init__(self, hass: HomeAssistant, access_token: str):
        """Initialize."""
        self.hass = hass
        self.access_token = access_token
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data = {}  # Dictionary of iso_timestamp -> price
        self.currency = None
        self._listeners = []
        self._retry_delay = 60
        self._scheduled_update_remove = None
        self._sorted_keys = []

    def async_add_listener(self, update_callback):
        """Listen for data updates."""
        self._listeners.append(update_callback)

        def remove_listener():
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    def _notify_listeners(self):
        """Notify listeners of new data."""
        for callback in self._listeners:
            callback()

    async def async_load(self):
        """Load data from cache and schedule updates."""
        try:
            stored = await self._store.async_load()
            if stored:
                if isinstance(stored, dict) and "data" in stored:
                     self.data = stored["data"]
                     self.currency = stored.get("currency")
                else:
                     # Legacy or simple format (just data dict)
                     self.data = stored
                     self.currency = None # Unknown

                self._update_sorted_keys()
                _LOGGER.info("Loaded cached Tibber prices")
        except Exception:
            _LOGGER.exception("Failed to load cached data")

        # Check if we need to fetch now (if cache is empty or stale)
        if not self._has_valid_data():
             await self.async_refresh()
        else:
             self._schedule_next_daily_update()

    def _has_valid_data(self):
        """Check if we have valid data for today."""
        if not self.data:
            return False

        # Check if we have data covering the current hour
        now = dt_util.now()
        for iso_ts in self.data:
             ts = dt_util.parse_datetime(iso_ts)
             if ts and ts.date() == now.date():
                 return True
        return False

    def _update_sorted_keys(self):
        """Update sorted keys list for binary search or linear scan."""
        # Convert keys to datetime objects and sort
        valid_keys = []
        for k in self.data:
            dt = dt_util.parse_datetime(k)
            if dt:
                valid_keys.append((dt, k)) # Store (datetime, original_key)
        valid_keys.sort(key=lambda x: x[0])
        self._sorted_keys = valid_keys

    async def async_refresh(self):
        """Fetch new data from API."""
        if self._scheduled_update_remove:
            self._scheduled_update_remove()
            self._scheduled_update_remove = None

        try:
            await self._fetch_data()
            self._retry_delay = 60  # Reset retry delay
            await self._save()
            self._update_sorted_keys()
            self._notify_listeners()
            self._schedule_next_daily_update()
        except Exception as err:
            _LOGGER.error("Error fetching data: %s", err)
            self._schedule_retry()

    async def _fetch_data(self):
        """Execute the API call."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        # Fetch current (for currency), today and tomorrow
        query = """
        {
          viewer {
            homes {
              currentSubscription {
                priceInfo {
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

        async with session.post(API_URL, json={"query": query}, headers=headers) as response:
            if response.status != 200:
                raise Exception(f"API returned status {response.status}")

            json_data = await response.json()
            if "errors" in json_data:
                raise Exception(f"API errors: {json_data['errors']}")

            data = json_data.get("data", {}).get("viewer", {}).get("homes", [])
            if not data:
                raise Exception("No homes found")

            price_info = data[0].get("currentSubscription", {}).get("priceInfo", {})

            current_info = price_info.get("current")
            if current_info:
                self.currency = current_info.get("currency")

            new_data = {}
            for day_key in ["today", "tomorrow"]:
                points = price_info.get(day_key, [])
                for point in points:
                    start_at = point["startsAt"]
                    total = point["total"]
                    new_data[start_at] = total

            if not new_data:
                 raise Exception("No price data returned from API")

            self.data = new_data

    async def _save(self):
        """Save data to disk."""
        try:
            await self._store.async_save({
                "data": self.data,
                "currency": self.currency
            })
        except Exception:
            _LOGGER.exception("Error saving cache")

    def _schedule_next_daily_update(self):
        """Schedule the next update for tomorrow at 15:05."""
        now = dt_util.now()
        # Target 15:05 today
        target = now.replace(hour=15, minute=5, second=0, microsecond=0)

        # If we are already past 15:05, schedule for tomorrow
        if now >= target:
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        # Add some jitter
        delay += random.uniform(0, 300)

        _LOGGER.debug("Scheduling next update in %s seconds (at %s)", delay, target)

        self._scheduled_update_remove = async_call_later(self.hass, delay, self._scheduled_refresh_wrapper)

    async def _scheduled_refresh_wrapper(self, _):
        """Wrapper for scheduled refresh."""
        await self.async_refresh()

    def _schedule_retry(self):
        """Schedule a retry with exponential backoff."""
        delay = self._retry_delay
        # Cap at 1 hour
        self._retry_delay = min(self._retry_delay * 2, 3600)

        _LOGGER.warning("Retrying in %s seconds", delay)
        self._scheduled_update_remove = async_call_later(self.hass, delay, self._scheduled_refresh_wrapper)

    def shutdown(self):
        """Cancel any scheduled updates."""
        if self._scheduled_update_remove:
            self._scheduled_update_remove()
            self._scheduled_update_remove = None

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
             # Check if data is stale (older than 1 hour)
             # Tibber prices are hourly or 15-min based.
             if (time_point - best_match_dt) < timedelta(hours=1):
                 return self.data[best_match_key]

        return None
