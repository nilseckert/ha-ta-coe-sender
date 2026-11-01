"""Aufbau von CoE-Paketen (CAN over Ethernet) für die Technische Alternative C.M.I.

Reines Python ohne Home-Assistant-Abhängigkeiten, damit es einzeln testbar ist.
Das Byte-Layout wurde gegen python-can-coe 0.1.1 (coe/messagebuilder.py)
abgeglichen.

V1 (UDP-Port 5441): 14 Bytes pro Paket
    [0]      Knotennummer des Absenders
    [1]      Block: analog 1..8 (je 4 Ausgänge), digital 0 (1-16) oder 9 (17-32)
    [2..9]   4 x int16 little endian (analog) bzw. 16-Bit-Maske in [2..3] (digital)
    [10..13] 4 x Einheiten-Code (0 = Slot unbelegt)

V2 (UDP-Port 5442): 4 Byte Kopf + 8 Byte je Wert, maximal 4 Werte pro Paket
    Kopf:  [2, 0, Gesamtlänge, Anzahl]
    Wert:  [Knoten, Ausgang-1, 0=digital/1=analog, Einheit, 4 Byte Wert (int32 LE)]
"""

from __future__ import annotations

from dataclasses import dataclass

COE_V1 = "V1"
COE_V2 = "V2"
DEFAULT_PORTS = {COE_V1: 5441, COE_V2: 5442}

UNIT_ONOFF = 43  # Einheiten-Code für digitale Werte in V2


class ProtocolError(ValueError):
    """Ungültige Eingabe für ein CoE-Paket."""


@dataclass(frozen=True)
class Item:
    """Ein zu sendender Wert.

    value ist bei analogen Werten bereits der skalierte Ganzzahlwert
    (z. B. 453 für 45,3 °C), bei digitalen Werten ein bool.
    """

    digital: bool
    output: int  # 1-basiert
    value: int | bool
    unit: int = 0


def max_output(version: str, digital: bool) -> int:
    """Höchste erlaubte Ausgangsnummer."""
    if version == COE_V1:
        return 32
    return 64


def validate_item(version: str, item: Item) -> None:
    """Prüft einen einzelnen Wert, wirft ProtocolError bei Verstoß."""
    if version not in DEFAULT_PORTS:
        raise ProtocolError(f"Unbekannte CoE-Version: {version}")
    limit = max_output(version, item.digital)
    if not 1 <= item.output <= limit:
        raise ProtocolError(f"Ausgang {item.output} außerhalb 1..{limit}")
    if item.digital:
        return
    if not 1 <= item.unit <= 255:
        raise ProtocolError(f"Ungültiger Einheiten-Code: {item.unit}")
    low, high = (-32768, 32767) if version == COE_V1 else (-(2**31), 2**31 - 1)
    if not low <= int(item.value) <= high:
        raise ProtocolError(
            f"Wert {item.value} außerhalb des Bereichs {low}..{high} (CoE {version})"
        )


def build_packets(version: str, node: int, items: list[Item]) -> list[bytes]:
    """Baut alle nötigen UDP-Payloads für die übergebenen Werte."""
    if not 1 <= node <= 62:
        raise ProtocolError(f"Knotennummer {node} außerhalb 1..62")
    seen: set[tuple[bool, int]] = set()
    for item in items:
        validate_item(version, item)
        key = (item.digital, item.output)
        if key in seen:
            raise ProtocolError(
                f"Ausgang {item.output} ({'digital' if item.digital else 'analog'}) doppelt belegt"
            )
        seen.add(key)
    if not items:
        return []
    if version == COE_V1:
        return _build_v1(node, items)
    return _build_v2(node, items)


def _build_v1(node: int, items: list[Item]) -> list[bytes]:
    groups: dict[tuple[bool, int], list[Item]] = {}
    for item in items:
        if item.digital:
            block = 0 if item.output <= 16 else 9
        else:
            block = (item.output - 1) // 4 + 1
        groups.setdefault((item.digital, block), []).append(item)

    packets: list[bytes] = []
    for (digital, block), members in sorted(groups.items()):
        data = bytearray(14)
        data[0] = node
        data[1] = block
        for item in members:
            if digital:
                idx = (item.output - 1) % 16
                if item.value:
                    data[2 + idx // 8] |= 1 << (idx % 8)
            else:
                pos = (item.output - 1) % 4
                data[2 + pos * 2 : 4 + pos * 2] = int(item.value).to_bytes(
                    2, "little", signed=True
                )
                data[10 + pos] = item.unit
        packets.append(bytes(data))
    return packets


def _build_v2(node: int, items: list[Item]) -> list[bytes]:
    packets: list[bytes] = []
    for digital in (False, True):
        members = sorted(
            (i for i in items if i.digital == digital), key=lambda i: i.output
        )
        for start in range(0, len(members), 4):
            chunk = members[start : start + 4]
            data = bytearray([2, 0, 4 + 8 * len(chunk), len(chunk)])
            for item in chunk:
                frame = bytearray(8)
                frame[0] = node
                frame[1] = item.output - 1
                if digital:
                    frame[2] = 0
                    frame[3] = UNIT_ONOFF
                    frame[4] = 1 if item.value else 0
                else:
                    frame[2] = 1
                    frame[3] = item.unit
                    frame[4:8] = int(item.value).to_bytes(4, "little", signed=True)
                data += frame
            packets.append(bytes(data))
    return packets
