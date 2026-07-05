from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import requests

DSD_NEO_VERSION = "v2.3.0"
DSD_NEO_URL = (
    "https://github.com/arancormonk/dsd-neo/releases/download/"
    f"{DSD_NEO_VERSION}/dsd-neo-msvc-x86_64-native-{DSD_NEO_VERSION.lstrip('v')}.zip"
)


def find_dsdneo(explicit_path: str, install_dir: Path) -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.append(install_dir / "dsd-neo.exe")
    candidates.append(shutil.which("dsd-neo") or Path())

    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def download_dsdneo(install_dir: Path, progress_callback=None) -> Path:
    install_dir.mkdir(parents=True, exist_ok=True)
    zip_path = install_dir / "dsd-neo.zip"

    with requests.get(DSD_NEO_URL, stream=True, timeout=120) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        with zip_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(downloaded / total)

    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(install_dir)
    zip_path.unlink(missing_ok=True)

    exe = install_dir / "dsd-neo.exe"
    if not exe.exists():
        matches = list(install_dir.rglob("dsd-neo.exe"))
        if not matches:
            raise FileNotFoundError("dsd-neo.exe not found in downloaded archive")
        exe = matches[0]
    return exe


def verify_dsdneo(exe_path: Path) -> tuple[bool, str]:
    if not exe_path.exists():
        return False, f"Decoder not found: {exe_path}"
    try:
        result = subprocess.run(
            [str(exe_path), "-h"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except OSError as exc:
        return False, str(exc)

    output = (result.stdout or "") + (result.stderr or "")
    if "dsd-neo" in output.lower() or result.returncode in {0, 1}:
        return True, "DSD-neo is ready"
    return False, output.strip() or "Unknown decoder response"


def list_rtl_devices(exe_path: Path) -> list[str]:
    if not exe_path.exists():
        return []
    try:
        result = subprocess.run(
            [str(exe_path), "-O"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except OSError:
        return []

    devices: list[str] = []
    for line in (result.stdout or "").splitlines():
        match = re.search(r"rtl\s*[:=]?\s*(\d+)", line, re.IGNORECASE)
        if match:
            devices.append(f"RTL-SDR #{match.group(1)}")
        elif "rtl" in line.lower() and line.strip():
            devices.append(line.strip())
    return devices or ["RTL-SDR #0 (default)"]
