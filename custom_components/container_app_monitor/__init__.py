"""The Container App Monitor integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ContainerAppMonitorWorker
from .repairs import async_remove_container_issue

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Container App Monitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    worker = ContainerAppMonitorWorker(hass, entry)
    await worker.async_start()

    hass.data[DOMAIN][entry.entry_id] = worker

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await async_remove_container_issue(hass, entry.entry_id)

    worker = hass.data[DOMAIN].get(entry.entry_id)
    if worker:
        await worker.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id)

    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)