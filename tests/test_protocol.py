"""Tests für den Paketbau. Die erwarteten Bytes stammen aus python-can-coe 0.1.1."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

_PATH = (
    Path(__file__).parent.parent / "custom_components" / "ta_coe_sender" / "protocol.py"
)
_spec = importlib.util.spec_from_file_location("ta_coe_protocol", _PATH)
protocol = importlib.util.module_from_spec(_spec)
sys.modules["ta_coe_protocol"] = protocol
_spec.loader.exec_module(protocol)

Item = protocol.Item
CELSIUS = 1


def test_v1_analog_two_values_one_block() -> None:
    packets = protocol.build_packets(
        "V1", 50, [Item(False, 1, 453, CELSIUS), Item(False, 3, -50, CELSIUS)]
    )
    assert [p.hex() for p in packets] == ["3201c5010000ceff000001000100"]


def test_v1_analog_blocks_are_split() -> None:
    packets = protocol.build_packets(
        "V1", 50, [Item(False, 1, 100, CELSIUS), Item(False, 5, 200, CELSIUS)]
    )
    assert len(packets) == 2
    assert packets[0][1] == 1
    assert packets[1][1] == 2


def test_v1_digital() -> None:
    items = [
        Item(True, 1, True),
        Item(True, 3, True),
        Item(True, 10, True),
        Item(True, 2, False),
    ]
    assert protocol.build_packets("V1", 50, items)[0].hex() == (
        "3200050200000000000000000000"
    )
    items = [Item(True, 17, True), Item(True, 32, True)]
    assert protocol.build_packets("V1", 50, items)[0].hex() == (
        "3209018000000000000000000000"
    )


def test_v2_analog() -> None:
    packets = protocol.build_packets(
        "V2", 50, [Item(False, 1, 453, CELSIUS), Item(False, 2, -50, CELSIUS)]
    )
    assert [p.hex() for p in packets] == ["0200140232000101c501000032010101ceffffff"]


def test_v2_digital() -> None:
    packets = protocol.build_packets(
        "V2", 50, [Item(True, 1, True), Item(True, 5, False)]
    )
    assert [p.hex() for p in packets] == ["020014023200002b010000003204002b00000000"]


def test_v2_more_than_four_values_are_chunked() -> None:
    items = [Item(False, i, i, CELSIUS) for i in range(1, 7)]
    packets = protocol.build_packets("V2", 50, items)
    assert [p[3] for p in packets] == [4, 2]


@pytest.mark.parametrize(
    ("version", "item"),
    [
        ("V1", Item(False, 1, 40000, CELSIUS)),  # > int16
        ("V1", Item(False, 33, 1, CELSIUS)),  # Ausgang zu hoch
        ("V1", Item(False, 1, 1, 0)),  # Einheit fehlt
        ("V2", Item(False, 65, 1, CELSIUS)),
        ("V3", Item(False, 1, 1, CELSIUS)),
    ],
)
def test_invalid_items_raise(version: str, item) -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.build_packets(version, 50, [item])


def test_duplicate_output_raises() -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.build_packets(
            "V1", 50, [Item(False, 1, 1, CELSIUS), Item(False, 1, 2, CELSIUS)]
        )


def test_invalid_node_raises() -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.build_packets("V1", 0, [Item(False, 1, 1, CELSIUS)])
