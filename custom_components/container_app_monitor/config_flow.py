"""Config flow for Container App Monitor."""
from __future__ import annotations

import os
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_get_container_apps(hass: HomeAssistant) -> dict[str, str]:
    """Fetch dictionary of installed container apps (Slug -> Friendly Name) from Supervisor REST API."""
    url = "http://supervisor/addons"
    token = os.environ.get("SUPERVISOR_TOKEN")
    
    if not token:
        _LOGGER.warning("SUPERVISOR_TOKEN not found. Running outside HAOS? Returning mock defaults.")
        return {"homeassistant": "Home Assistant", "core_ssh": "SSH & Web Terminal", "core_file_editor": "File editor"}

    headers = {"Authorization": f"Bearer {token}"}
    session = async_get_clientsession(hass)

    apps = {}
    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                addons = data.get("data", {}).get("addons", [])
                for addon in addons:
                    slug = addon.get("slug")
                    name = addon.get("name", slug)
                    if slug:
                        apps[slug] = name
                return apps
            _LOGGER.error("Failed to fetch apps from Supervisor API, status: %s", response.status)
    except Exception as err:
        _LOGGER.error("Error connecting to Supervisor API for app discovery: %s", err)

    return apps

class ContainerAppMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Container App Monitor."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow for reconfiguration."""
        return ContainerAppMonitorOptionsFlow()

    async def async_step_user(self, user_input: dict[str, any] | None = None) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        app_map = await async_get_container_apps(self.hass)

        if user_input is not None:
            selected_slug = user_input["app_name"]
            friendly_name = app_map.get(selected_slug, selected_slug)
            return self.async_create_entry(
                title=f"Monitor: {friendly_name}", data=user_input
            )

        if not app_map:
            errors["base"] = "no_apps_found"
            app_options = {"none": "No Apps Found"}
        else:
            app_options = app_map

        schema = vol.Schema({
            vol.Required("app_name"): vol.In(app_options),
            vol.Required("expected_state", default="running"): vol.In(["running", "not running"]),
        })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )


class ContainerAppMonitorOptionsFlow(config_entries.OptionsFlow):
    """Handle options/reconfiguration for Container App Monitor."""

    async def async_step_init(self, user_input: dict[str, any] | None = None) -> FlowResult:
        """Manage the reconfiguration options step."""
        errors: dict[str, str] = {}
        app_map = await async_get_container_apps(self.hass)

        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=user_input,
                title=f"Monitor: {app_map.get(user_input['app_name'], user_input['app_name'])}"
            )
            return self.async_create_entry(title="", data={})

        if not app_map:
            app_options = {self.config_entry.data.get("app_name", "none"): "Current App"}
        else:
            app_options = app_map

        current_app = self.config_entry.data.get("app_name")
        current_state = self.config_entry.data.get("expected_state", "running")

        schema = vol.Schema({
            vol.Required("app_name", default=current_app): vol.In(app_options),
            vol.Required("expected_state", default=current_state): vol.In(["running", "not running"]),
        })

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )