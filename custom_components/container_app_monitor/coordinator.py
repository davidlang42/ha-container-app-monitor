"""Data update coordinator for Container App Monitor."""
from __future__ import annotations

import os
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .repairs import async_create_container_issue, async_remove_container_issue

_LOGGER = logging.getLogger(__name__)

class ContainerAppMonitorCoordinator(DataUpdateCoordinator[dict[str, any]]):
    """Class to manage fetching container states via Supervisor API and reconciling repairs."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, any]:
        """Fetch container status from Supervisor and handle issues."""
        app_name = self.entry.data.get("app_name")
        expected_state = self.entry.data.get("expected_state", "running")

        if not app_name:
            return {"is_running": False}

        is_running = await self._check_container_running(app_name)

        mismatch = (expected_state == "running" and not is_running) or \
                   (expected_state == "not running" and is_running)

        if mismatch:
            await async_create_container_issue(
                self.hass, self.entry.entry_id, app_name, expected_state
            )
        else:
            await async_remove_container_issue(self.hass, self.entry.entry_id)

        return {"is_running": is_running, "app_name": app_name}

    async def _check_container_running(self, app_name: str) -> bool:
        """Query Supervisor API to check if container add-on is currently running."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return True # Fallback assumption if testing outside HAOS

        url = f"http://supervisor/addons/{app_name}/info"
        headers = {"Authorization": f"Bearer {token}"}
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    res_data = await response.json()
                    state = res_data.get("data", {}).get("state")
                    # Supervisor states: "started", "stopped"
                    return state == "started"
        except Exception as err:
            _LOGGER.error("Failed to check container state for %s: %s", app_name, err)

        return False