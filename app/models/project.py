from dataclasses import dataclass, field
from datetime import date

from .cable import Cable
from .patch_panel import PatchPanel
from .daq import DaqCrate

APP_VERSION = "1.0"


@dataclass
class Project:
    name: str = "Untitled Project"
    version: str = APP_VERSION
    created: str = field(default_factory=lambda: date.today().isoformat())
    cables: list = field(default_factory=list)
    patch_panels: list = field(default_factory=list)
    crates: list = field(default_factory=list)

    def cable_by_id(self, cid: str):
        return next((c for c in self.cables if c.id == cid), None)

    def next_cable_id(self, prefix: str = "CBL") -> str:
        existing = {c.id for c in self.cables}
        n = 1
        while True:
            candidate = f"{prefix}-{n:03d}"
            if candidate not in existing:
                return candidate
            n += 1

    def next_panel_id(self) -> str:
        existing = {p.id for p in self.patch_panels}
        n = 1
        while True:
            candidate = f"PP{n:02d}"
            if candidate not in existing:
                return candidate
            n += 1

    def next_crate_id(self) -> str:
        existing = {c.id for c in self.crates}
        n = 1
        while True:
            candidate = f"CRATE{n:02d}"
            if candidate not in existing:
                return candidate
            n += 1

    def to_dict(self) -> dict:
        return {
            "project": {
                "name": self.name,
                "version": self.version,
                "created": self.created,
            },
            "cables": [c.to_dict() for c in self.cables],
            "patch_panels": [p.to_dict() for p in self.patch_panels],
            "daq_system": {
                "crates": [cr.to_dict() for cr in self.crates],
            },
        }

    @staticmethod
    def from_dict(d: dict) -> "Project":
        meta = d.get("project", {})
        proj = Project(
            name=meta.get("name", "Untitled Project"),
            version=meta.get("version", APP_VERSION),
            created=meta.get("created", date.today().isoformat()),
        )
        proj.cables = [Cable.from_dict(c) for c in d.get("cables", [])]
        proj.patch_panels = [PatchPanel.from_dict(p) for p in d.get("patch_panels", [])]
        proj.crates = [DaqCrate.from_dict(cr) for cr in d.get("daq_system", {}).get("crates", [])]
        return proj
