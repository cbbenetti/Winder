from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PatchPort:
    id: str = ""
    row: int = 0
    col: int = 0
    front_cable_id: str = ""
    rear_cable_id: str = ""
    label: str = ""
    signal_type: str = "Analog"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "row": self.row,
            "col": self.col,
            "front_cable_id": self.front_cable_id,
            "rear_cable_id": self.rear_cable_id,
            "label": self.label,
            "signal_type": self.signal_type,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "PatchPort":
        return PatchPort(
            id=d.get("id", ""),
            row=int(d.get("row", 0)),
            col=int(d.get("col", 0)),
            front_cable_id=d.get("front_cable_id", ""),
            rear_cable_id=d.get("rear_cable_id", ""),
            label=d.get("label", ""),
            signal_type=d.get("signal_type", "Analog"),
            notes=d.get("notes", ""),
        )


@dataclass
class PatchPanel:
    id: str = ""
    name: str = ""
    rows: int = 4
    cols: int = 12
    ports: list = field(default_factory=list)

    def port_at(self, row: int, col: int) -> Optional[PatchPort]:
        for p in self.ports:
            if p.row == row and p.col == col:
                return p
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "rows": self.rows,
            "cols": self.cols,
            "ports": [p.to_dict() for p in self.ports],
        }

    @staticmethod
    def from_dict(d: dict) -> "PatchPanel":
        panel = PatchPanel(
            id=d.get("id", ""),
            name=d.get("name", ""),
            rows=int(d.get("rows", 4)),
            cols=int(d.get("cols", 12)),
        )
        panel.ports = [PatchPort.from_dict(p) for p in d.get("ports", [])]
        return panel
