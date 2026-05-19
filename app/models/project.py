from dataclasses import dataclass, field
from datetime import date

from .cable import Cable, CableBundle
from .patch_panel import PatchPanel
from .daq import DaqCrate

APP_VERSION = "1.0"


@dataclass
class Project:
    name: str = "Untitled Project"
    version: str = APP_VERSION
    created: str = field(default_factory=lambda: date.today().isoformat())
    author: str = ""
    description: str = ""
    revision: str = ""
    modified: str = ""
    cables: list = field(default_factory=list)
    patch_panels: list = field(default_factory=list)
    crates: list = field(default_factory=list)
    bundles: list = field(default_factory=list)

    def all_endpoint_ids(self) -> list[str]:
        ids = set()
        for panel in self.patch_panels:
            for port in panel.ports:
                ids.add(port.id)
                ids.add(f"{port.id}:rear")
        for crate in self.crates:
            for slot in crate.slots:
                if slot.module:
                    for ch in slot.module.channels:
                        ids.add(ch.id)
        return sorted(ids)

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

    def rename_cable(self, old_id: str, new_id: str) -> bool:
        """Rename cable ID and propagate to all refs. Returns False on collision."""
        if not new_id or new_id == old_id:
            return False
        if any(c.id == new_id for c in self.cables):
            return False
        cable = self.cable_by_id(old_id)
        if cable is None:
            return False
        cable.id = new_id
        for crate in self.crates:
            for slot in crate.slots:
                if slot.module:
                    for ch in slot.module.channels:
                        if ch.cable_id == old_id:
                            ch.cable_id = new_id
        for panel in self.patch_panels:
            for port in panel.ports:
                if port.front_cable_id == old_id:
                    port.front_cable_id = new_id
                if port.rear_cable_id == old_id:
                    port.rear_cable_id = new_id
        for bundle in self.bundles:
            bundle.cable_ids = [new_id if cid == old_id else cid for cid in bundle.cable_ids]
        return True

    def to_dict(self) -> dict:
        return {
            "project": {
                "name": self.name,
                "version": self.version,
                "created": self.created,
                "author": self.author,
                "description": self.description,
                "revision": self.revision,
                "modified": self.modified,
            },
            "cables": [c.to_dict() for c in self.cables],
            "bundles": [b.to_dict() for b in self.bundles],
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
            author=meta.get("author", ""),
            description=meta.get("description", ""),
            revision=meta.get("revision", ""),
            modified=meta.get("modified", ""),
        )
        proj.cables = [Cable.from_dict(c) for c in d.get("cables", [])]
        proj.bundles = [CableBundle.from_dict(b) for b in d.get("bundles", [])]
        proj.patch_panels = [PatchPanel.from_dict(p) for p in d.get("patch_panels", [])]
        proj.crates = [DaqCrate.from_dict(cr) for cr in d.get("daq_system", {}).get("crates", [])]
        return proj
