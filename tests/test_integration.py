"""Config Flow, Options Flow und Senden gegen einen echten UDP-Socket."""

from __future__ import annotations

import asyncio
import socket

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ta_coe_sender.const import DOMAIN


@pytest.fixture
def fake_cmi(socket_enabled):
    """UDP-Socket, der die C.M.I. spielt (Sockets sind im Test-HA sonst gesperrt)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(3)
    yield sock
    sock.close()


async def _recv(sock: socket.socket) -> bytes:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, lambda: sock.recvfrom(64)[0])
    return data


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.50", "version": "V1", "node": 50},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": "192.168.1.50", "version": "V1", "node": 50}
    assert result["options"]["mappings"] == []


async def test_duplicate_entry_is_aborted(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.50", "version": "V1", "node": 50},
        unique_id="192.168.1.50_50",
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.50", "version": "V1", "node": 50},
    )
    assert result["type"] is FlowResultType.ABORT


async def test_options_flow_add_and_remove_mapping(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "version": "V1", "node": 50, "port": 9},
        options={"mappings": [], "interval": 60},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_mapping"}
    )
    # Einheit ohne Standard-Dezimalstellen -> Fehler
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "entity_id": "sensor.vorlauf",
            "kind": "analog",
            "output": 1,
            "unit": "bar",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"decimals": "decimals_required"}
    # Ausgang außerhalb von V1
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "entity_id": "sensor.vorlauf",
            "kind": "analog",
            "output": 40,
            "unit": "celsius",
        },
    )
    assert result["errors"] == {"output": "output_out_of_range"}
    # Gültig: °C mit Standard-Dezimalstellen
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "entity_id": "sensor.vorlauf",
            "kind": "analog",
            "output": 1,
            "unit": "celsius",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"] == [
        {
            "entity_id": "sensor.vorlauf",
            "kind": "analog",
            "output": 1,
            "unit": "celsius",
            "decimals": 1,
        }
    ]

    # Entfernen
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_mapping"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"remove": ["0"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["mappings"] == []


async def test_sends_on_state_change(hass: HomeAssistant, fake_cmi) -> None:
    port = fake_cmi.getsockname()[1]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "version": "V1", "node": 50, "port": port},
        options={
            "interval": 3600,
            "mappings": [
                {
                    "entity_id": "sensor.vorlauf",
                    "kind": "analog",
                    "output": 1,
                    "unit": "celsius",
                    "decimals": 1,
                },
                {"entity_id": "binary_sensor.pumpe", "kind": "digital", "output": 2},
            ],
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.vorlauf", "45.3")
    hass.states.async_set("binary_sensor.pumpe", "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Start-Senden (HA läuft im Test bereits): analoger und digitaler Block
    first = {await _recv(fake_cmi), await _recv(fake_cmi)}
    assert bytes.fromhex("3201c50100000000000001000000") in first
    assert bytes.fromhex("3200000000000000000000000000") in first

    # Änderung -> sofort neu senden
    hass.states.async_set("sensor.vorlauf", "46.0")
    hass.states.async_set("binary_sensor.pumpe", "on")
    await hass.async_block_till_done()
    seen = set()
    for _ in range(4):
        try:
            seen.add(await _recv(fake_cmi))
        except TimeoutError:
            break
    assert bytes.fromhex("3201cc0100000000000001000000") in seen  # 460
    assert bytes.fromhex("3200020000000000000000000000") in seen  # Ausgang 2


async def test_unavailable_value_is_not_sent(hass: HomeAssistant, fake_cmi) -> None:
    port = fake_cmi.getsockname()[1]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "version": "V1", "node": 50, "port": port},
        options={
            "interval": 3600,
            "mappings": [
                {
                    "entity_id": "sensor.vorlauf",
                    "kind": "analog",
                    "output": 1,
                    "unit": "celsius",
                    "decimals": 1,
                }
            ],
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.vorlauf", "unavailable")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    fake_cmi.settimeout(0.5)
    with pytest.raises(TimeoutError):
        await _recv(fake_cmi)
