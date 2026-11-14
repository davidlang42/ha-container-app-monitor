"""Repair flows and issue registry manager for Container App Monitor."""
from __future__ import annotations

import os
import logging
import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str] | None
) -> RepairsFlow:
    """Create the fix flow handler instantly without blocking awaits."""
    return ContainerRepairFlow(issue_id, data)

class ContainerRepairFlow(RepairsFlow):
    """Handler for fixing container state discrepancies interactively via Supervisor API."""

    def __init__(self, issue_id: str, data: dict[str, str] | None) -> None:
        """Initialize repair flow parameters."""
        self.issue_id = issue_id
        self.data = data or {}

    def _get_entry_info(self) -> tuple[str, str]:
        """Helper to retrieve app_name and expected_state from config entry."""
        entry_id = self.issue_id.replace("mismatch_", "")
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == entry_id:
                return (
                    entry.data.get("app_name", "unknown"),
                    entry.data.get("expected_state", "running"),
                )
        return "unknown", "running"

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> RepairsFlowResult:
        """Step 1: Display confirmation modal and container logs. Clicking Submit proceeds to step 2."""
        if user_input is not None and user_input.get("confirm_step") == "1":
            return await self.async_step_confirm()

        app_name, expected_state = self._get_entry_info()
        friendly_name = await self._get_friendly_name(app_name)
        logs = await self._get_app_logs(app_name)
        action_upper = "START" if expected_state == "running" else "STOP"

        schema = vol.Schema({
            vol.Optional("confirm_step", default="1"): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "app_name": app_name,
                "friendly_name": friendly_name,
                "action_upper": action_upper,
                "logs": logs,
            },
        )

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> RepairsFlowResult:
        """Step 2: Execute remediation ONLY when the form in step 1 is submitted."""
        app_name, expected_state = self._get_entry_info()
        await self._execute_remediation(app_name, expected_state)
        return self.async_create_entry(title="", data={})

    async def _execute_remediation(self, app_name: str, expected_state: str) -> None:
        """Trigger container start or stop via Supervisor REST endpoint."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token or app_name == "unknown":
            _LOGGER.warning("Cannot execute remediation: Invalid token or app_name.")
            return

        action = "start" if expected_state == "running" else "stop"
        url = f"http://supervisor/addons/{app_name}/{action}"
        headers = {"Authorization": f"Bearer {token}"}
        session = async_get_clientsession(self.hass)

        try:
            async with session.post(url, headers=headers, timeout=30) as response:
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.error("Failed to %s container %s: %s", action, app_name, text)
        except Exception as err:
            _LOGGER.error("Exception occurred during container %s remediation: %s", action, err)

    async def _get_friendly_name(self, app_name: str) -> str:
        """Look up add-on friendly name from Supervisor API."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return app_name

        url = f"http://supervisor/addons/{app_name}/info"
        headers = {"Authorization": f"Bearer {token}"}
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    res_data = await response.json()
                    return res_data.get("data", {}).get("name", app_name)
        except Exception:
            pass
        return app_name

    async def _get_app_logs(self, app_name: str) -> str:
        """Retrieve recent stdout log lines from the container app via Supervisor logs API."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return "No supervisor token found for log retrieval."

        url = f"http://supervisor/addons/{app_name}/logs/latest?lines=50"
        headers = {"Authorization": f"Bearer {token}"}
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    return await response.text()
                return f"Unable to fetch logs (HTTP status {response.status})"
        except Exception as err:
            _LOGGER.error("Exception fetching container logs for %s: %s", app_name, err)
            return f"Error loading logs: {err}"

async def async_create_container_issue(
    hass: HomeAssistant, entry_id: str, app_name: str, friendly_name: str, expected_state: str
) -> None:
    """Create a persistent interactive repair issue for container state violation."""
    severity = (
        ir.IssueSeverity.ERROR
        if expected_state == "running"
        else ir.IssueSeverity.WARNING
    )
    target_state = "running" if expected_state == "running" else "stopped"

    ir.async_create_issue(
        hass,
        domain=DOMAIN,
        issue_id=f"mismatch_{entry_id}",
        is_fixable=True,
        severity=severity,
        translation_key="state_mismatch",
        translation_placeholders={
            "app_name": app_name,
            "friendly_name": friendly_name,
            "target_state": target_state,
        },
    )

async def async_remove_container_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Automatically remove issue if resolved manually or via normal health checks."""
    ir.async_delete_issue(hass, domain=DOMAIN, issue_id=f"mismatch_{entry_id}")