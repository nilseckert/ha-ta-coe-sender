"""TA CoE Sender: sendet Home-Assistant-Werte per CoE (UDP) an eine Technische-Alternative-C.M.I."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INTERVAL,
    CONF_MAPPINGS,
    CONF_NODE,
    CONF_VERSION,
    DEFAULT_INTERVAL,
)
from .protocol import DEFAULT_PORTS
from .sender import CoESender

type CoESenderConfigEntry = ConfigEntry[CoESender]


async def async_setup_entry(hass: HomeAssistant, entry: CoESenderConfigEntry) -> bool:
    """Konfigurationseintrag einrichten."""
    version = entry.data[CONF_VERSION]
    sender = CoESender(
        hass,
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT) or DEFAULT_PORTS[version],
        version=version,
        node=entry.data[CONF_NODE],
        mappings=list(entry.options.get(CONF_MAPPINGS, [])),
        interval=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL),
    )
    sender.async_start()
    entry.runtime_data = sender
    entry.async_on_unload(sender.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CoESenderConfigEntry) -> bool:
    """Eintrag entladen; Listener werden über async_on_unload entfernt."""
    return True


async def _async_reload_on_update(
    hass: HomeAssistant, entry: CoESenderConfigEntry
) -> None:
    """Bei geänderten Optionen neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
