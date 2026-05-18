from dataclasses import dataclass
from pathlib import Path
import json

CONFIG_DIR = Path.home() / ".config" / "winder"
CONFIG_FILE = CONFIG_DIR / "crate_configs.json"

_DEFAULTS = [
    {"id": "vme-std",   "name": "VME Standard",   "crate_type": "VME",   "num_slots": 20, "description": "Standard 20-slot VME crate"},
    {"id": "camac-std", "name": "CAMAC Standard",  "crate_type": "CAMAC", "num_slots": 25, "description": "Standard 25-station CAMAC crate"},
    {"id": "nim-bin",   "name": "NIM Bin",         "crate_type": "NIM",   "num_slots": 12, "description": "Standard 12-slot NIM bin"},
]


@dataclass
class CrateConfig:
    id: str
    name: str
    crate_type: str
    num_slots: int
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "crate_type": self.crate_type,
            "num_slots": self.num_slots,
            "description": self.description,
        }

    @staticmethod
    def from_dict(d: dict) -> "CrateConfig":
        return CrateConfig(
            id=d["id"],
            name=d["name"],
            crate_type=d["crate_type"],
            num_slots=int(d["num_slots"]),
            description=d.get("description", ""),
        )


def load_configs() -> list[CrateConfig]:
    if not CONFIG_FILE.exists():
        return [CrateConfig.from_dict(d) for d in _DEFAULTS]
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return [CrateConfig.from_dict(d) for d in json.load(f)]


def save_configs(configs: list[CrateConfig]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in configs], f, indent=2)
