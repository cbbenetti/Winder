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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_number": self.channel_number,
            "cable_id": self.cable_id,
            "signal_label": self.signal_label,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "DaqChannel":
        return DaqChannel(
            id=d.get("id", ""),
            channel_number=int(d.get("channel_number", 0)),
            cable_id=d.get("cable_id", ""),
            signal_label=d.get("signal_label", ""),
            notes=d.get("notes", ""),
        )


@dataclass
class DaqSlot:
    id: str = ""
    slot_number: int = 0
    module_type: str = "ADC"
    model: str = ""
    channels: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slot_number": self.slot_number,
            "module_type": self.module_type,
            "model": self.model,
            "channels": [ch.to_dict() for ch in self.channels],
        }

    @staticmethod
    def from_dict(d: dict) -> "DaqSlot":
        slot = DaqSlot(
            id=d.get("id", ""),
            slot_number=int(d.get("slot_number", 0)),
            module_type=d.get("module_type", "ADC"),
            model=d.get("model", ""),
        )
        slot.channels = [DaqChannel.from_dict(ch) for ch in d.get("channels", [])]
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
