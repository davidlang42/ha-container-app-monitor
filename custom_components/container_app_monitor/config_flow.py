"""Config flow for Container App Monitor."""
from __future__ import annotations

import os
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_get_container_apps(hass: HomeAssistant) -> list[str]:
    """Fetch list of currently installed container apps from Supervisor REST API."""
    url = "http://supervisor/addons"
    token = os.environ.get("SUPERVISOR_TOKEN")
    
    if not token:
        _LOGGER.warning("SUPERVISOR_TOKEN not found. Running outside HAOS? Returning mock defaults.")
        return ["homeassistant", "core_ssh", "core_duckdns"]

    headers = {"Authorization": f"Bearer {token}"}
    session = async_get_clientsession(hass)

    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                addons = data.get("data", {}).get("addons", [])
                return [addon["slug"] for addon in addons]
            _LOGGER.error("Failed to fetch apps from Supervisor API, status: %s", response.status)
    except Exception as err:
        _LOGGER.error("Error connecting to Supervisor API for app discovery: %s", err)

    return []

class ContainerAppMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Container App Monitor."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, any] | None = None) -> FlowResult:
        """Handle the initial step invoked via UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"Monitor: {user_input['app_name']}", data=user_input
            )

        app_options = await async_get_container_apps(self.hass)
        if not app_options:
            errors["base"] = "no_apps_found"

        schema = vol.Schema({
            vol.Required("app_name"): vol.In(app_options if app_options else ["none"]),
            vol.Required("expected_state", default="running"): vol.In(["running", "not running"]),
        })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )