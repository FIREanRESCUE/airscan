from __future__ import annotations

from pathlib import Path

from airscan.models import ChannelEntry, Protocol, ScannerSystem, SystemType, Talkgroup


def write_channel_map(path: Path, channels: list[ChannelEntry]) -> None:
    lines = ["ChannelNumber(dec),frequency(Hz),note"]
    for channel in channels:
        lines.append(channel.to_csv_row())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_talkgroup_list(path: Path, talkgroups: list[Talkgroup]) -> None:
    lines = ["DEC,Mode(A=Allow; B=Block; DE=Enc),Name,Tag"]
    for tg in talkgroups:
        lines.append(tg.to_csv_row())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_trunk_scan_targets(path: Path, systems: list[ScannerSystem], runtime_dir: Path) -> None:
    lines = [
        "id,type,frequency_hz,chan_csv,dwell_ms,activity_hold_ms,notes,modulation,rtl_gain"
    ]
    for index, system in enumerate(systems):
        target_id = f"sys{index + 1}"
        chan_csv = ""
        if system.channels and system.system_type == SystemType.TRUNKED:
            chan_path = runtime_dir / f"{target_id}_channels.csv"
            write_channel_map(chan_path, system.channels)
            chan_csv = str(chan_path.resolve())

        scan_type = _scan_type(system)
        modulation = system.modulation if system.modulation != "auto" else ""
        lines.append(
            f"{target_id},{scan_type},{system.control_frequency_hz},{chan_csv},"
            f"3000,,{system.name},{modulation},{system.gain or 'auto'}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_system_files(system: ScannerSystem, runtime_dir: Path) -> tuple[Path | None, Path | None]:
    chan_path: Path | None = None
    group_path: Path | None = None

    if system.channels:
        chan_path = runtime_dir / "channels.csv"
        write_channel_map(chan_path, system.channels)

    if system.talkgroups:
        group_path = runtime_dir / "talkgroups.csv"
        write_talkgroup_list(group_path, system.talkgroups)

    return chan_path, group_path


def _scan_type(system: ScannerSystem) -> str:
    if system.protocol == Protocol.DMR_CONVENTIONAL:
        return "dmr-conventional"
    if system.protocol == Protocol.DMR_TRUNK:
        return "dmr-trunk"
    if system.protocol in {Protocol.NXDN48, Protocol.NXDN96}:
        return "dmr-trunk"
    return "p25-trunk"
