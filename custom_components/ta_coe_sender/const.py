"""Konstanten für TA CoE Sender."""

from __future__ import annotations

DOMAIN = "ta_coe_sender"

CONF_VERSION = "version"
CONF_NODE = "node"
CONF_INTERVAL = "interval"
CONF_MAPPINGS = "mappings"
CONF_KIND = "kind"
CONF_OUTPUT = "output"
CONF_UNIT = "unit"
CONF_DECIMALS = "decimals"

KIND_ANALOG = "analog"
KIND_DIGITAL = "digital"

DEFAULT_NODE = 50
DEFAULT_INTERVAL = 60  # Sekunden

# Einheiten-Codes laut python-can-coe (CoEType). Dezimalstellen sind der
# Skalierungsfaktor der CoE-Ganzzahl: Wert * 10**Dezimalstellen.
# Nur für °C ist ein Standard hinterlegt; bei allen anderen Einheiten muss die
# Dezimalstellen-Zahl laut TA-Tabelle der Messgrößen selbst angegeben werden.
UNITS: dict[str, dict] = {
    "celsius": {"label": "°C (Temperatur)", "code": 1, "decimals": 1},
    "kelvin": {"label": "K (Kelvin)", "code": 7, "decimals": None},
    "percent": {"label": "% (Prozent)", "code": 8, "decimals": None},
    "kilowatt": {"label": "kW", "code": 9, "decimals": None},
    "kwh": {"label": "kWh", "code": 11, "decimals": None},
    "volts": {"label": "V (Volt)", "code": 12, "decimals": None},
    "milliamp": {"label": "mA", "code": 13, "decimals": None},
    "hertz": {"label": "Hz", "code": 19, "decimals": None},
    "liters_h": {"label": "l/h", "code": 3, "decimals": None},
    "liters_min": {"label": "l/min", "code": 20, "decimals": None},
    "bar": {"label": "bar", "code": 21, "decimals": None},
}
