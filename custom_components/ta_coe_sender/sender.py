"""Sendet gemappte Home-Assistant-Zustände als CoE-UDP-Pakete an die C.M.I."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import socket
from typing import Any

from homeassistant.const import CONF_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started

from .const import (
    CONF_DECIMALS,
    CONF_KIND,
    CONF_OUTPUT,
    CONF_UNIT,
    KIND_DIGITAL,
    UNITS,
)
from .protocol import Item, ProtocolError, build_packets, validate_item

_LOGGER = logging.getLogger(__name__)

_TRUE_STATES = {"on", "true", "1"}


class CoESender:
    """Sendet bei Zustandsänderung sofort und zusätzlich zyklisch."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        version: str,
        node: int,
        mappings: list[dict[str, Any]],
        interval: int,
    ) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._version = version
        self._node = node
        self._mappings = mappings
        self._interval = interval
        self._unsubs: list[CALLBACK_TYPE] = []
        self._lock = asyncio.Lock()
        self._warned: set[str] = set()
        self._send_failing = False

    @callback
    def async_start(self) -> None:
        """Listener registrieren und nach dem HA-Start einmal senden."""
        entity_ids = sorted({m[CONF_ENTITY_ID] for m in self._mappings})
        if entity_ids:
            self._unsubs.append(
                async_track_state_change_event(
                    self._hass, entity_ids, self._handle_state_change
                )
            )
        self._unsubs.append(
            async_track_time_interval(
                self._hass, self._handle_timer, timedelta(seconds=self._interval)
            )
        )
        if (unsub := async_at_started(self._hass, self._handle_started)) is not None:
            self._unsubs.append(unsub)

    @callback
    def async_stop(self) -> None:
        """Alle Listener entfernen."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _handle_started(self, hass: HomeAssistant) -> None:
        await self.async_send()

    @callback
    def _handle_state_change(self, event: Event) -> None:
        self._hass.async_create_task(self.async_send())

    async def _handle_timer(self, now: Any) -> None:
        await self.async_send()

    def _collect_items(self) -> list[Item]:
        items: list[Item] = []
        for mapping in self._mappings:
            entity_id = mapping[CONF_ENTITY_ID]
            state = self._hass.states.get(entity_id)
            # Nicht verfügbare Werte werden bewusst NICHT gesendet: so läuft der
            # Timeout des CAN-Eingangs in der UVR ab und deren Ersatzwert greift,
            # statt dass ein alter Wert als gültig erscheint.
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            try:
                if mapping[CONF_KIND] == KIND_DIGITAL:
                    item = Item(
                        digital=True,
                        output=int(mapping[CONF_OUTPUT]),
                        value=state.state.lower() in _TRUE_STATES,
                    )
                else:
                    decimals = int(mapping[CONF_DECIMALS])
                    unit = UNITS[mapping[CONF_UNIT]]["code"]
                    item = Item(
                        digital=False,
                        output=int(mapping[CONF_OUTPUT]),
                        value=round(float(state.state) * 10**decimals),
                        unit=unit,
                    )
                validate_item(self._version, item)
            except (ValueError, KeyError, ProtocolError) as err:
                self._warn_once(entity_id, state.state, err)
                continue
            self._warned.discard(entity_id)
            items.append(item)
        return items

    def _warn_once(self, entity_id: str, value: str, err: Exception) -> None:
        if entity_id in self._warned:
            return
        self._warned.add(entity_id)
        _LOGGER.warning(
            "%s: Wert %r kann nicht als CoE gesendet werden: %s", entity_id, value, err
        )

    async def async_send(self) -> None:
        """Alle aktuell gültigen Werte senden."""
        items = self._collect_items()
        if not items:
            return
        try:
            packets = build_packets(self._version, self._node, items)
        except ProtocolError as err:
            _LOGGER.error("CoE-Paket konnte nicht gebaut werden: %s", err)
            return
        async with self._lock:
            try:
                await self._hass.async_add_executor_job(self._send_blocking, packets)
            except OSError as err:
                if not self._send_failing:
                    _LOGGER.warning(
                        "Senden an %s:%s fehlgeschlagen: %s",
                        self._host,
                        self._port,
                        err,
                    )
                self._send_failing = True
                return
            if self._send_failing:
                _LOGGER.info("Senden an %s:%s funktioniert wieder", self._host, self._port)
            self._send_failing = False

    def _send_blocking(self, packets: list[bytes]) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            for packet in packets:
                _LOGGER.debug(
                    "CoE %s -> %s:%s: %s",
                    self._version,
                    self._host,
                    self._port,
                    packet.hex(),
                )
                sock.sendto(packet, (self._host, self._port))
