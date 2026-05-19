from dataclasses import dataclass, field


CRATE_TYPES = ["VME", "CAMAC", "NIM", "Other"]
MODULE_TYPES = ["ADC", "TDC", "QDC", "Discriminator", "Fan-out", "Scaler", "Logic", "DAC", "Pattern Unit", "Other"]


@dataclass
class DaqChannel:
    id: str = ""
    channel_number: int = 0
    cable_id: str = ""
    signal_label: str = ""
    notes: str = ""
    role: str = "input"       # "input" | "output"
    connector: str = ""       # ConnectorSpec name this channel belongs to

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_number": self.channel_number,
            "cable_id": self.cable_id,
            "signal_label": self.signal_label,
            "notes": self.notes,
            "role": self.role,
            "connector": self.connector,
        }

    @staticmethod
    def from_dict(d: dict) -> "DaqChannel":
        return DaqChannel(
            id=d.get("id", ""),
            channel_number=int(d.get("channel_number", 0)),
            cable_id=d.get("cable_id", ""),
            signal_label=d.get("signal_label", ""),
            notes=d.get("notes", ""),
            role=d.get("role", "input"),
            connector=d.get("connector", ""),
        )


@dataclass
class DaqModule:
    id: str = ""
    name: str = ""
    module_type: str = "ADC"
    definition_id: str = ""
    color: str = "#546e7a"
    channel_start: int = 0
    channels: list = field(default_factory=list)  # list[DaqChannel]
    collapsed: bool = False
    coupled_io: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "module_type": self.module_type,
            "definition_id": self.definition_id,
            "color": self.color,
            "channel_start": self.channel_start,
            "channels": [ch.to_dict() for ch in self.channels],
            "collapsed": self.collapsed,
            "coupled_io": self.coupled_io,
        }

    @staticmethod
    def from_dict(d: dict) -> "DaqModule":
        mod = DaqModule(
            id=d.get("id", ""),
            name=d.get("name", ""),
            module_type=d.get("module_type", "ADC"),
            definition_id=d.get("definition_id", ""),
            color=d.get("color", "#546e7a"),
            channel_start=int(d.get("channel_start", 0)),
            collapsed=bool(d.get("collapsed", False)),
            coupled_io=bool(d.get("coupled_io", False)),
        )
        mod.channels = [DaqChannel.from_dict(ch) for ch in d.get("channels", [])]
        return mod


@dataclass
class DaqSlot:
    id: str = ""
    slot_number: int = 0
    module_type: str = "ADC"
    model: str = ""
    module: DaqModule | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "slot_number": self.slot_number,
            "module_type": self.module_type,
            "model": self.model,
        }
        if self.module is not None:
            d["module"] = self.module.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "DaqSlot":
        slot = DaqSlot(
            id=d.get("id", ""),
            slot_number=int(d.get("slot_number", 0)),
            module_type=d.get("module_type", "ADC"),
            model=d.get("model", ""),
        )
        if "module" in d and d["module"]:
            slot.module = DaqModule.from_dict(d["module"])
        elif "channels" in d and d["channels"]:
            # Migrate old format: channels lived directly on the slot
            slot.module = DaqModule(
                id=slot.id + "-MOD",
                name=slot.model or slot.module_type,
                module_type=slot.module_type,
                channels=[DaqChannel.from_dict(ch) for ch in d["channels"]],
            )
        return slot


@dataclass
class DaqCrate:
    id: str = ""
    name: str = ""
    crate_type: str = "VME"
    slots: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "crate_type": self.crate_type,
            "slots": [s.to_dict() for s in self.slots],
        }

    @staticmethod
    def from_dict(d: dict) -> "DaqCrate":
        crate = DaqCrate(
            id=d.get("id", ""),
            name=d.get("name", ""),
            crate_type=d.get("crate_type", "VME"),
        )
        crate.slots = [DaqSlot.from_dict(s) for s in d.get("slots", [])]
        return crate
