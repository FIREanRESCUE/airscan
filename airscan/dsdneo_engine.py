from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from airscan.csv_generator import prepare_system_files, write_trunk_scan_targets
from airscan.dsdneo_setup import format_pulse_input
from airscan.models import AppSettings, InputSource, Protocol, ScannerSystem, SystemType


@dataclass
class CallEvent:
    timestamp: float
    text: str
    talkgroup: str = ""
    frequency: str = ""
    protocol: str = ""


class DsdNeoEngine:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._event_queue: queue.Queue[CallEvent | str] = queue.Queue()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    @property
    def events(self) -> queue.Queue[CallEvent | str]:
        return self._event_queue

    def stop(self) -> None:
        self._running = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def start_system(
        self,
        exe_path: Path,
        system: ScannerSystem,
        settings: AppSettings,
        runtime_dir: Path,
        recordings_dir: Path,
    ) -> list[str]:
        self.stop()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        recordings_dir.mkdir(parents=True, exist_ok=True)

        chan_path, group_path = prepare_system_files(system, runtime_dir)
        command = self._build_command(
            exe_path, system, settings, runtime_dir, recordings_dir, chan_path, group_path
        )
        return self._launch(command, runtime_dir)

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
        return self._launch(command, runtime_dir)

    def _launch(self, command: list[str], runtime_dir: Path) -> list[str]:
        event_log = runtime_dir / "events.log"
        event_log.write_text("", encoding="utf-8")

        self._event_queue.put(f"Starting: {' '.join(command)}")
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        self._running = True
        self._reader_thread = threading.Thread(
            target=self._read_output,
            args=(event_log,),
            daemon=True,
        )
        self._reader_thread.start()
        return command

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

    def _read_output(self, event_log: Path) -> None:
        assert self._process and self._process.stdout
        last_size = 0
        while self._running:
            line = self._process.stdout.readline()
            if line:
                parsed = self._parse_line(line.rstrip())
                self._event_queue.put(parsed)
            elif self._process.poll() is not None:
                break

            if event_log.exists():
                size = event_log.stat().st_size
                if size > last_size:
                    new_text = event_log.read_text(encoding="utf-8", errors="replace")[last_size:]
                    for event_line in new_text.splitlines():
                        parsed = self._parse_line(event_line)
                        self._event_queue.put(parsed)
                    last_size = size
            time.sleep(0.05)

        code = self._process.poll() if self._process else None
        self._running = False
        self._event_queue.put(f"Decoder stopped (exit code {code})")

    def _parse_line(self, line: str) -> CallEvent | str:
        if not line.strip():
            return line

        tg_match = re.search(r"(?:TG|TGT|Talkgroup|Group)\s*[:#]?\s*(\d+)", line, re.IGNORECASE)
        freq_match = re.search(r"(\d{3,4}\.\d{4,6})\s*MHz", line, re.IGNORECASE)
        proto_match = re.search(r"\b(P25|DMR|NXDN|D-?STAR)\b", line, re.IGNORECASE)

        if tg_match or freq_match or "voice" in line.lower() or "grant" in line.lower():
            return CallEvent(
                timestamp=time.time(),
                text=line,
                talkgroup=tg_match.group(1) if tg_match else "",
                frequency=freq_match.group(1) if freq_match else "",
                protocol=proto_match.group(1).upper() if proto_match else "",
            )
        return line
