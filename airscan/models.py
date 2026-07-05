from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Protocol(str, Enum):
    P25_PHASE1 = "p25_phase1"
    P25_PHASE2 = "p25_phase2"
    P25_TRUNK = "p25_trunk"
    DMR_TRUNK = "dmr_trunk"
    DMR_CONVENTIONAL = "dmr_conventional"
    NXDN48 = "nxdn48"
    NXDN96 = "nxdn96"
    AUTO = "auto"


class SystemType(str, Enum):
    TRUNKED = "trunked"
    CONVENTIONAL = "conventional"


class InputSource(str, Enum):
    RTL_SDR = "rtl_sdr"
    LINE_IN = "line_in"


@dataclass
class ChannelEntry:
    channel_number: int
    frequency_hz: int
    note: str = ""

    def to_csv_row(self) -> str:
        note = f",{self.note}" if self.note else ""
        return f"{self.channel_number},{self.frequency_hz}{note}"


@dataclass
class Talkgroup:
    talkgroup_id: int
    mode: str = "A"
    name: str = ""
    tag: str = ""

    def to_csv_row(self) -> str:
        tag = f",{self.tag}" if self.tag else ""
        return f"{self.talkgroup_id},{self.mode},{self.name}{tag}"


@dataclass
class ScannerSystem:
    name: str
    protocol: Protocol
    system_type: SystemType = SystemType.TRUNKED
    control_frequency_hz: int = 0
    channels: list[ChannelEntry] = field(default_factory=list)
    talkgroups: list[Talkgroup] = field(default_factory=list)
    input_source: InputSource = InputSource.RTL_SDR
    rtl_device: int = 0
    gain: int = 0
    ppm: int = 0
    bandwidth: int = 12
    audio_device: str = ""
    input_volume: int = 1
    rigctl_port: int = 0
    use_trunking: bool = True
    use_whitelist: bool = False
    modulation: str = "auto"
    notes: str = ""

    def frequency_mhz(self) -> str:
        mhz = self.control_frequency_hz / 1_000_000
        if mhz >= 1000:
            return f"{mhz:.3f}G"
        return f"{mhz:.3f}M"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["protocol"] = self.protocol.value
        data["system_type"] = self.system_type.value
        data["input_source"] = self.input_source.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScannerSystem:
        return cls(
            name=data["name"],
            protocol=Protocol(data["protocol"]),
            system_type=SystemType(data.get("system_type", "trunked")),
            control_frequency_hz=int(data.get("control_frequency_hz", 0)),
            channels=[
                ChannelEntry(
                    channel_number=int(c["channel_number"]),
                    frequency_hz=int(c["frequency_hz"]),
                    note=c.get("note", ""),
                )
                for c in data.get("channels", [])
            ],
            talkgroups=[
                Talkgroup(
                    talkgroup_id=int(t["talkgroup_id"]),
                    mode=t.get("mode", "A"),
                    name=t.get("name", ""),
                    tag=t.get("tag", ""),
                )
                for t in data.get("talkgroups", [])
            ],
            input_source=InputSource(data.get("input_source", InputSource.RTL_SDR.value)),
            rtl_device=int(data.get("rtl_device", 0)),
            gain=int(data.get("gain", 0)),
            ppm=int(data.get("ppm", 0)),
            bandwidth=int(data.get("bandwidth", 12)),
            audio_device=str(data.get("audio_device", "")),
            input_volume=int(data.get("input_volume", 1)),
            rigctl_port=int(data.get("rigctl_port", 0)),
            use_trunking=bool(data.get("use_trunking", True)),
            use_whitelist=bool(data.get("use_whitelist", False)),
            modulation=str(data.get("modulation", "auto")),
            notes=str(data.get("notes", "")),
        )


@dataclass
class AppSettings:
    dsdneo_path: str = ""
    recordings_dir: str = "recordings"
    auto_record: bool = True
    hang_time: float = 1.0
    block_encrypted: bool = False
    default_audio_device: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        return cls(
            dsdneo_path=str(data.get("dsdneo_path", "")),
            recordings_dir=str(data.get("recordings_dir", "recordings")),
            auto_record=bool(data.get("auto_record", True)),
            hang_time=float(data.get("hang_time", 1.0)),
            block_encrypted=bool(data.get("block_encrypted", False)),
            default_audio_device=str(data.get("default_audio_device", "")),
        )
