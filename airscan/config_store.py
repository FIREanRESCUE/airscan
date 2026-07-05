from __future__ import annotations

import json
from pathlib import Path

from airscan.models import AppSettings, ScannerSystem

DEFAULT_CONFIG = {
    "settings": AppSettings().to_dict(),
    "systems": [],
}


class ConfigStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent
        self.data_dir = self.base_dir / "data"
        self.config_path = self.data_dir / "config.json"
        self.runtime_dir = self.base_dir / "runtime"
        self.recordings_dir = self.base_dir / "recordings"
        self.dsdneo_dir = self.base_dir / "tools" / "dsd-neo"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.dsdneo_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> tuple[AppSettings, list[ScannerSystem]]:
        self.ensure_dirs()
        if not self.config_path.exists():
            self.save(AppSettings(), [])
            return AppSettings(), []

        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        settings = AppSettings.from_dict(raw.get("settings", {}))
        systems = [ScannerSystem.from_dict(item) for item in raw.get("systems", [])]
        return settings, systems

    def save(self, settings: AppSettings, systems: list[ScannerSystem]) -> None:
        self.ensure_dirs()
        payload = {
            "settings": settings.to_dict(),
            "systems": [system.to_dict() for system in systems],
        }
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def system_runtime_dir(self, system_name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in system_name)
        path = self.runtime_dir / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def default_dsdneo_exe(self) -> Path:
        return self.dsdneo_dir / "dsd-neo.exe"
