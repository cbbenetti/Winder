from dataclasses import dataclass
from pathlib import Path
import json

CONFIG_DIR = Path.home() / ".config" / "winder"
CONFIG_FILE = CONFIG_DIR / "cable_types.json"

CONNECTOR_TYPES = ["BNC", "SMA", "LEMO", "SHV", "RJ45", "DB9", "LC", "Ribbon", "Bare", "Other"]

_DEFAULTS = [
    {"id": "RG58",         "name": "RG58",         "color": "#4fc3f7", "connector_type": "BNC",    "default_signal_type": "Analog"},
    {"id": "RG59",         "name": "RG59",         "color": "#29b6f6", "connector_type": "BNC",    "default_signal_type": "Analog"},
    {"id": "RG62",         "name": "RG62",         "color": "#0288d1", "connector_type": "BNC",    "default_signal_type": "Analog"},
    {"id": "Twisted Pair", "name": "Twisted Pair", "color": "#66bb6a", "connector_type": "RJ45",   "default_signal_type": "Digital"},
    {"id": "STP",          "name": "STP",          "color": "#43a047", "connector_type": "RJ45",   "default_signal_type": "Digital"},
    {"id": "Fiber",        "name": "Fiber",        "color": "#ab47bc", "connector_type": "LC",     "default_signal_type": "Digital"},
    {"id": "HV",           "name": "HV",           "color": "#ef5350", "connector_type": "SHV",    "default_signal_type": "HV"},
    {"id": "Ribbon",       "name": "Ribbon",       "color": "#78909c", "connector_type": "Ribbon", "default_signal_type": "Other"},
    {"id": "Other",        "name": "Other",        "color": "#9e9e9e", "connector_type": "Bare",   "default_signal_type": "Other"},
]


@dataclass
class CableType:
    id: str
    name: str
    color: str
    connector_type: str
    default_signal_type: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "connector_type": self.connector_type,
            "default_signal_type": self.default_signal_type,
        }

    @staticmethod
    def from_dict(d: dict) -> "CableType":
        return CableType(
            id=d["id"],
            name=d["name"],
            color=d["color"],
            connector_type=d.get("connector_type", "BNC"),
            default_signal_type=d.get("default_signal_type", "Analog"),
        )


def load_cable_types() -> list[CableType]:
    if not CONFIG_FILE.exists():
        return [CableType.from_dict(d) for d in _DEFAULTS]
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return [CableType.from_dict(d) for d in json.load(f)]


def save_cable_types(types: list[CableType]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in types], f, indent=2)
