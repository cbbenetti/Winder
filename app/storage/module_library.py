from dataclasses import dataclass, field
from pathlib import Path
import json

CONFIG_DIR = Path.home() / ".config" / "winder"
CONFIG_FILE = CONFIG_DIR / "module_library.json"

CONNECTOR_TYPES = ["single", "ribbon"]

_DEFAULTS = [
    {
        "id": "caen-v785",
        "name": "CAEN V785",
        "color": "#2e7d32",
        "module_type": "ADC",
        "num_channels": 32,
        "channel_start": 0,
        "inputs":  [{"name": "Signal In", "type": "ribbon", "num_channels": 32}],
        "outputs": [],
    },
    {
        "id": "caen-v775",
        "name": "CAEN V775",
        "color": "#1565c0",
        "module_type": "TDC",
        "num_channels": 32,
        "channel_start": 0,
        "inputs":  [{"name": "Signal In", "type": "ribbon", "num_channels": 32}],
        "outputs": [],
    },
    {
        "id": "phillips-776",
        "name": "Phillips 776",
        "color": "#e65100",
        "module_type": "Discriminator",
        "num_channels": 16,
        "channel_start": 0,
        "inputs":  [{"name": "Signal In", "type": "ribbon", "num_channels": 16}],
        "outputs": [{"name": "NIM Out",   "type": "ribbon", "num_channels": 16}],
    },
    {
        "id": "shaper-16ch",
        "name": "Shaper (16ch)",
        "color": "#6a1b9a",
        "module_type": "Other",
        "num_channels": 16,
        "channel_start": 1,
        "inputs":  [{"name": "Signal In",   "type": "ribbon", "num_channels": 16}],
        "outputs": [
            {"name": "Shaper Slow", "type": "ribbon", "num_channels": 16},
            {"name": "Shaper Fast", "type": "ribbon", "num_channels": 16},
        ],
    },
]


@dataclass
class ConnectorSpec:
    name: str = ""
    type: str = "single"
    num_channels: int = 1

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type, "num_channels": self.num_channels}

    @staticmethod
    def from_dict(d: dict) -> "ConnectorSpec":
        return ConnectorSpec(
            name=d.get("name", ""),
            type=d.get("type", "single"),
            num_channels=int(d.get("num_channels", 1)),
        )


@dataclass
class ModuleDefinition:
    id: str = ""
    name: str = ""
    color: str = "#546e7a"
    module_type: str = "ADC"
    num_channels: int = 0
    channel_start: int = 0
    inputs: list = field(default_factory=list)   # list[ConnectorSpec]
    outputs: list = field(default_factory=list)  # list[ConnectorSpec]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "module_type": self.module_type,
            "num_channels": self.num_channels,
            "channel_start": self.channel_start,
            "inputs":  [c.to_dict() for c in self.inputs],
            "outputs": [c.to_dict() for c in self.outputs],
        }

    @staticmethod
    def from_dict(d: dict) -> "ModuleDefinition":
        defn = ModuleDefinition(
            id=d.get("id", ""),
            name=d.get("name", ""),
            color=d.get("color", "#546e7a"),
            module_type=d.get("module_type", "ADC"),
            num_channels=int(d.get("num_channels", 0)),
            channel_start=int(d.get("channel_start", 0)),
        )
        defn.inputs  = [ConnectorSpec.from_dict(c) for c in d.get("inputs",  [])]
        defn.outputs = [ConnectorSpec.from_dict(c) for c in d.get("outputs", [])]
        return defn


def load_module_library() -> list[ModuleDefinition]:
    if not CONFIG_FILE.exists():
        return [ModuleDefinition.from_dict(d) for d in _DEFAULTS]
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return [ModuleDefinition.from_dict(d) for d in json.load(f)]


def save_module_library(defs: list[ModuleDefinition]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump([d.to_dict() for d in defs], f, indent=2)
