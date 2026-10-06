"""Repair flows and issue registry manager for Container App Monitor."""
from __future__ import annotations

import os
import logging
import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow, async_create_issue, async_delete_issue
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ContainerRepairFlow(RepairsFlow):
    """Handler for fixing container state discrepancies interactively via Supervisor API."""

    def __init__(self, hass: HomeAssistant, entry_id: str, app_name: str, expected_state: str) -> None:
        """Initialize repair flow parameters."""
        self.hass = hass
        self.entry_id = entry_id
        self.app_name = app_name
        self.expected_state = expected_state

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Handle initial step: preview logs and request confirmation to start/stop."""
        if user_input is not None:
            await self._execute_remediation()
            return self.async_create_entry(title="", data={})

        logs = await self._get_app_logs(self.app_name)

        return self.async_show_form(
            step_id="init",
            description_placeholders={
                "app_name": self.app_name,
                "expected_state": self.expected_state,
                "logs": logs,
            },
            data_schema=vol.Schema({}),
        )

    async def _execute_remediation(self) -> None:
        """Trigger container start or stop via Supervisor REST endpoint."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            _LOGGER.warning("Missing SUPERVISOR_TOKEN; cannot execute remediation command.")
            return

        # Action endpoint mapping: /addons/{slug}/start or /addons/{slug}/stop
        action = "start" if self.expected_state == "running" else "stop"
        url = f"http://supervisor/addons/{self.app_name}/{action}"
        headers = {"Authorization": f"Bearer {token}"}
        session = async_get_clientsession(self.hass)

        try:
            async with session.post(url, headers=headers, timeout=30) as response:
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.error("Failed to %s container %s: %s", action, self.app_name, text)
        except Exception as err:
            _LOGGER.error("Exception occurred during container %s remediation: %s", action, err)

    async def _get_app_logs(self, app_name: str) -> str:
        """Retrieve recent stdout log lines from the container app via Supervisor logs API."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return "No supervisor token found for log retrieval."

        # Supervisor API endpoint for latest app container logs
        url = f"http://supervisor/addons/{app_name}/logs/latest?lines=50"
        headers = {"Authorization": f"Bearer {token}"}
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    # Logs endpoint returns text/plain output stream
                    return await response.text()
                return f"Unable to fetch logs (HTTP status {response.status})"
        except Exception as err:
            _LOGGER.error("Exception fetching container logs for %s: %s", app_name, err)
            return f"Error loading logs: {err}"

async def async_create_container_issue(
    hass: HomeAssistant, entry_id: str, app_name: str, expected_state: str
) -> None:
    """Create a persistent interactive repair issue for container state violation."""
    async_create_issue(
        hass,
        domain=DOMAIN,
        issue_id=f"mismatch_{entry_id}",
        is_fixable=True,
        severity="error",
        translation_key="state_mismatch",
        translation_placeholders={
            "app_name": app_name,
            "expected_state": expected_state,
        },
    )

async def async_remove_container_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Automatically remove issue if resolved manually or via normal health checks."""
    async_delete_issue(hass, domain=DOMAIN, issue_id=f"mismatch_{entry_id}")

async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str] | None
) -> RepairsFlow | None:
    """Create flow handler when user clicks fix on the repair issue dialog."""
    if issue_id.startswith("mismatch_"):
        entry_id = issue_id.replace("mismatch_", "")
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == entry_id:
                return ContainerRepairFlow(
                    hass=hass,
                    entry_id=entry_id,
                    app_name=entry.data.get("app_name", "unknown_app"),
                    expected_state=entry.data.get("expected_state", "running"),
                )
    return None