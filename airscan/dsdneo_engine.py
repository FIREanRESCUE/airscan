from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from airscan.csv_generator import prepare_system_files, write_trunk_scan_targets
from airscan.dsdneo_setup import format_pulse_input
from airscan.models import AppSettings, InputSource, Protocol, ScannerSystem, SystemType


@dataclass
class CallEvent:
    timestamp: float
    text: str
    session: str = ""
    talkgroup: str = ""
    frequency: str = ""
    protocol: str = ""


@dataclass
class DecoderSession:
    name: str
    process: subprocess.Popen
    reader_thread: threading.Thread
    running: bool = True
    command: list[str] = field(default_factory=list)


class DsdNeoEngine:
    def __init__(self) -> None:
        self._sessions: dict[str, DecoderSession] = {}
        self._session_system_meta: dict[str, ScannerSystem] = {}
        self._event_queue: queue.Queue[CallEvent | str] = queue.Queue()
        self._lock = threading.Lock()

    @property
    def events(self) -> queue.Queue[CallEvent | str]:
        return self._event_queue

    @property
    def running(self) -> bool:
        return bool(self.active_sessions())

    @property
    def active_session_names(self) -> list[str]:
        return list(self.active_sessions().keys())

    def active_sessions(self) -> dict[str, DecoderSession]:
        alive: dict[str, DecoderSession] = {}
        for name, session in self._sessions.items():
            if session.running and session.process.poll() is None:
                alive[name] = session
        return alive

    def stop(self) -> None:
        with self._lock:
            names = list(self._sessions.keys())
        for name in names:
            self.stop_session(name)

    def stop_session(self, name: str) -> None:
        with self._lock:
            session = self._sessions.pop(name, None)
        if not session:
            return
        session.running = False
        if session.process.poll() is None:
            session.process.terminate()
            try:
                session.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                session.process.kill()
        code = session.process.poll()
        self._event_queue.put(f"[{name}] Decoder stopped (exit code {code})")

    def start_system(
        self,
        exe_path: Path,
        system: ScannerSystem,
        settings: AppSettings,
        runtime_dir: Path,
        recordings_dir: Path,
        *,
        stop_others: bool = True,
    ) -> list[str]:
        if stop_others:
            self.stop()
        else:
            self.stop_session(system.name)

        conflict = self._input_conflict(system, exclude=system.name)
        if conflict:
            raise ValueError(conflict)

        runtime_dir.mkdir(parents=True, exist_ok=True)
        session_recordings = recordings_dir / _safe_dir_name(system.name)
        session_recordings.mkdir(parents=True, exist_ok=True)

        chan_path, group_path = prepare_system_files(system, runtime_dir)
        command = self._build_command(
            exe_path, system, settings, runtime_dir, session_recordings, chan_path, group_path
        )
        return self._launch(system.name, command, runtime_dir)

    def start_all_systems(
        self,
        exe_path: Path,
        systems: list[ScannerSystem],
        settings: AppSettings,
        runtime_root: Path,
        recordings_dir: Path,
    ) -> list[list[str]]:
        if not systems:
            raise ValueError("No systems configured.")

        rtl_systems = [s for s in systems if s.input_source == InputSource.RTL_SDR]
        if len(rtl_systems) < 2:
            raise ValueError("Multi-dongle mode needs at least two RTL-SDR systems.")

        conflict = self._validate_multi_inputs(rtl_systems)
        if conflict:
            raise ValueError(conflict)

        self.stop()
        commands: list[list[str]] = []
        for system in rtl_systems:
            runtime = runtime_root / _safe_dir_name(system.name)
            commands.append(
                self.start_system(
                    exe_path,
                    system,
                    settings,
                    runtime,
                    recordings_dir,
                    stop_others=False,
                )
            )
        return commands

    def start_trunk_scan(
        self,
        exe_path: Path,
        systems: list[ScannerSystem],
        settings: AppSettings,
        runtime_dir: Path,
        recordings_dir: Path,
    ) -> list[str]:
        self.stop()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        recordings_dir.mkdir(parents=True, exist_ok=True)

        targets = runtime_dir / "trunk_scan_targets.csv"
        write_trunk_scan_targets(targets, systems, runtime_dir)
        command = [
            str(exe_path),
            "-fa",
            "-T",
            f"--trunk-scan={targets}",
            f"-i=rtl:{systems[0].rtl_device}:{systems[0].frequency_mhz()}:"
            f"{systems[0].gain}:{systems[0].ppm}:{systems[0].bandwidth}",
            f"-t={settings.hang_time:g}",
            "-J",
            str(runtime_dir / "events.log"),
        ]
        if settings.auto_record:
            command.extend(["-P", "-7", str(recordings_dir)])
        if settings.block_encrypted:
            command.append("--enc-lockout")
        return self._launch("__trunk_scan__", command, runtime_dir)

    def _launch(self, session_name: str, command: list[str], runtime_dir: Path) -> list[str]:
        event_log = runtime_dir / "events.log"
        event_log.write_text("", encoding="utf-8")

        self._event_queue.put(f"[{session_name}] Starting: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        reader = threading.Thread(
            target=self._read_output,
            args=(session_name, process, event_log),
            daemon=True,
        )
        session = DecoderSession(name=session_name, process=process, reader_thread=reader, command=command)
        with self._lock:
            self._sessions[session_name] = session
        reader.start()
        return command

    def _validate_multi_inputs(self, systems: list[ScannerSystem]) -> str | None:
        seen_rtl: dict[int, str] = {}
        for system in systems:
            if system.input_source != InputSource.RTL_SDR:
                continue
            owner = seen_rtl.get(system.rtl_device)
            if owner:
                return (
                    f"Dongle #{system.rtl_device} is assigned to both '{owner}' and '{system.name}'. "
                    "Each running system needs its own RTL-SDR device index."
                )
            seen_rtl[system.rtl_device] = system.name
        return None

    def _input_conflict(self, system: ScannerSystem, exclude: str = "") -> str | None:
        active = self.active_sessions()
        for name, meta in self._session_system_meta.items():
            if name not in active or name == exclude:
                continue
            if system.input_source == InputSource.RTL_SDR and meta.input_source == InputSource.RTL_SDR:
                if system.rtl_device == meta.rtl_device:
                    return f"Dongle #{system.rtl_device} is already in use by '{name}'."
            if system.input_source == InputSource.LINE_IN and meta.input_source == InputSource.LINE_IN:
                if system.audio_device == meta.audio_device:
                    label = system.audio_device or "default"
                    return f"Audio input '{label}' is already in use by '{name}'."
        return None

    def register_system_meta(self, session_name: str, system: ScannerSystem) -> None:
        self._session_system_meta[session_name] = system

    def _build_command(
        self,
        exe_path: Path,
        system: ScannerSystem,
        settings: AppSettings,
        runtime_dir: Path,
        recordings_dir: Path,
        chan_path: Path | None,
        group_path: Path | None,
    ) -> list[str]:
        mode_flags = self._mode_flags(system)
        command = [str(exe_path), *mode_flags]

        if system.use_trunking and system.system_type == SystemType.TRUNKED:
            command.append("-T")

        command.extend(["-i", self._input_arg(system, settings), f"-t={settings.hang_time:g}"])

        if system.input_source == InputSource.LINE_IN and system.input_volume > 1:
            command.extend(["--input-volume", str(max(1, min(16, system.input_volume)))])

        if system.rigctl_port > 0:
            command.extend(["-U", str(system.rigctl_port)])

        if chan_path:
            command.extend(["-C", str(chan_path)])
        if group_path:
            command.extend(["-G", str(group_path)])
            if system.use_whitelist:
                command.append("-W")

        if settings.auto_record:
            command.extend(["-P", "-7", str(recordings_dir)])

        if settings.block_encrypted:
            command.append("--enc-lockout")

        command.extend(["-J", str(runtime_dir / "events.log")])

        mod = self._modulation_flag(system)
        if mod:
            command.append(mod)

        return command

    def _input_arg(self, system: ScannerSystem, settings: AppSettings) -> str:
        if system.input_source == InputSource.LINE_IN:
            device = system.audio_device or settings.default_audio_device
            return format_pulse_input(device)

        return (
            f"rtl:{system.rtl_device}:{system.frequency_mhz()}:"
            f"{system.gain}:{system.ppm}:{system.bandwidth}"
        )

    def _mode_flags(self, system: ScannerSystem) -> list[str]:
        mapping = {
            Protocol.AUTO: ["-fa"],
            Protocol.P25_PHASE1: ["-f1"],
            Protocol.P25_PHASE2: ["-f2", "-m2"],
            Protocol.P25_TRUNK: ["-ft"],
            Protocol.DMR_TRUNK: ["-fs"],
            Protocol.DMR_CONVENTIONAL: ["-fs"],
            Protocol.NXDN48: ["-fi"],
            Protocol.NXDN96: ["-fn"],
        }
        return mapping.get(system.protocol, ["-fa"])

    def _modulation_flag(self, system: ScannerSystem) -> str | None:
        mod = system.modulation.lower()
        if mod == "cqpsk":
            return "-mq"
        if mod == "c4fm":
            return "-mc"
        if mod == "gfsk":
            return "-mg"
        return None

    def _read_output(self, session_name: str, process: subprocess.Popen, event_log: Path) -> None:
        assert process.stdout
        last_size = 0
        running = True
        while running:
            with self._lock:
                session = self._sessions.get(session_name)
                running = bool(session and session.running)
            if not running:
                break

            line = process.stdout.readline()
            if line:
                self._event_queue.put(self._parse_line(line.rstrip(), session_name))
            elif process.poll() is not None:
                break

            if event_log.exists():
                size = event_log.stat().st_size
                if size > last_size:
                    new_text = event_log.read_text(encoding="utf-8", errors="replace")[last_size:]
                    for event_line in new_text.splitlines():
                        self._event_queue.put(self._parse_line(event_line, session_name))
                    last_size = size
            time.sleep(0.05)

        code = process.poll()
        with self._lock:
            session = self._sessions.get(session_name)
            if session:
                session.running = False
        self._event_queue.put(f"[{session_name}] Decoder stopped (exit code {code})")

    def _parse_line(self, line: str, session_name: str) -> CallEvent | str:
        if not line.strip():
            return f"[{session_name}]"

        tg_match = re.search(r"(?:TG|TGT|Talkgroup|Group)\s*[:#]?\s*(\d+)", line, re.IGNORECASE)
        freq_match = re.search(r"(\d{3,4}\.\d{4,6})\s*MHz", line, re.IGNORECASE)
        proto_match = re.search(r"\b(P25|DMR|NXDN|D-?STAR)\b", line, re.IGNORECASE)

        if tg_match or freq_match or "voice" in line.lower() or "grant" in line.lower():
            return CallEvent(
                timestamp=time.time(),
                session=session_name,
                text=line,
                talkgroup=tg_match.group(1) if tg_match else "",
                frequency=freq_match.group(1) if freq_match else "",
                protocol=proto_match.group(1).upper() if proto_match else "",
            )
        return f"[{session_name}] {line}"


def _safe_dir_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name) or "session"
