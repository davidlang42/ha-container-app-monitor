"""Background monitor worker for Container App Monitor."""
from __future__ import annotations

import os
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .repairs import async_create_container_issue, async_remove_container_issue

_LOGGER = logging.getLogger(__name__)

class ContainerAppMonitorWorker:
    """Class to manage periodic background checking of container states via Supervisor API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize worker."""
        self.hass = hass
        self.entry = entry
        self._unsub_interval = None

    async def async_start(self) -> None:
        """Start periodic tracking."""
        await self._async_check_state()

        self._unsub_interval = async_track_time_interval(
            self.hass,
            self._handle_interval,
            timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def async_stop(self) -> None:
        """Stop periodic tracking."""
        if self._unsub_interval:
            self._unsub_interval()
            self._unsub_interval = None

    async def _handle_interval(self, _now) -> None:
        """Handle time interval callback."""
        await self._async_check_state()

    async def _async_check_state(self) -> None:
        """Fetch container status from Supervisor and handle issues."""
        app_name = self.entry.data.get("app_name")
        expected_state = self.entry.data.get("expected_state", "running")

        if not app_name:
            return

        is_running, friendly_name = await self._get_container_info(app_name)

        mismatch = (expected_state == "running" and not is_running) or \
                   (expected_state == "not running" and is_running)

        if mismatch:
            await async_create_container_issue(
                self.hass, self.entry.entry_id, app_name, friendly_name, expected_state
            )
        else:
            await async_remove_container_issue(self.hass, self.entry.entry_id)

    async def _get_container_info(self, app_name: str) -> tuple[bool, str]:
        """Query Supervisor API to check running state and friendly name of container add-on."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return True, app_name

        url = f"http://supervisor/addons/{app_name}/info"
        headers = {"Authorization": f"Bearer {token}"}
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    res_data = await response.json()
                    data = res_data.get("data", {})
                    state = data.get("state")
                    friendly_name = data.get("name", app_name)
                    return (state == "started"), friendly_name
        except Exception as err:
            _LOGGER.error("Failed to check container state for %s: %s", app_name, err)

        return False, app_name