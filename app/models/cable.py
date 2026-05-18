from dataclasses import dataclass, field


CABLE_TYPES = ["RG58", "RG59", "RG62", "Twisted Pair", "STP", "Fiber", "HV", "Ribbon", "Other"]
SIGNAL_TYPES = ["Analog", "Digital", "HV", "Timing", "Trigger", "Power", "Other"]


@dataclass
class CableBundle:
    id: str = ""
    name: str = ""
    cable_ids: list = field(default_factory=list)
    color: str = "#78909c"

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "cable_ids": list(self.cable_ids), "color": self.color}

    @staticmethod
    def from_dict(d: dict) -> "CableBundle":
        return CableBundle(
            id=d.get("id", ""),
            name=d.get("name", ""),
            cable_ids=list(d.get("cable_ids", [])),
            color=d.get("color", "#78909c"),
        )


@dataclass
class Cable:
    id: str = ""
    label: str = ""
    cable_type: str = "RG58"
    signal_type: str = "Analog"
    from_endpoint: str = ""
    to_endpoint: str = ""
    length_m: float = 0.0
    notes: str = ""
    direction: str = ""   # "" | "→ forward" | "← reverse" | "↔ both"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "cable_type": self.cable_type,
            "signal_type": self.signal_type,
            "from_endpoint": self.from_endpoint,
            "to_endpoint": self.to_endpoint,
            "length_m": self.length_m,
            "notes": self.notes,
            "direction": self.direction,
        }

    def cable_type_color(self) -> str:
        from app.storage.cable_type import load_cable_types
        return next((ct.color for ct in load_cable_types() if ct.id == self.cable_type), "#9e9e9e")

    @staticmethod
    def from_dict(d: dict) -> "Cable":
        return Cable(
            id=d.get("id", ""),
            label=d.get("label", ""),
            cable_type=d.get("cable_type", "RG58"),
            signal_type=d.get("signal_type", "Analog"),
            from_endpoint=d.get("from_endpoint", ""),
            to_endpoint=d.get("to_endpoint", ""),
            length_m=float(d.get("length_m", 0.0)),
            notes=d.get("notes", ""),
            direction=d.get("direction", ""),
        )
