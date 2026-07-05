from __future__ import annotations

import queue
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from airscan.config_store import ConfigStore
from airscan.dsdneo_engine import CallEvent, DsdNeoEngine
from airscan.dsdneo_setup import find_dsdneo, list_audio_devices, list_rtl_devices, verify_dsdneo
from airscan.gui.setup_dialog import SetupDialog
from airscan.gui.system_editor import PROTOCOL_LABELS, SystemEditor
from airscan.models import AppSettings, InputSource, Protocol, ScannerSystem, SystemType


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.store = ConfigStore()
        self.settings, self.systems = self.store.load()
        self.engine = DsdNeoEngine()
        self.selected_index: int | None = None

        self.title("AirScan — Multi-Protocol Digital Scanner")
        self.geometry("1100x720")
        self.minsize(900, 600)

        self._build_layout()
        self._refresh_system_list()
        self.after(300, self._poll_events)
        self.after(500, self._maybe_show_setup)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            header,
            text="AirScan",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="P25 · DMR · NXDN · RTL-SDR or radio aux input",
            text_color="#aaaaaa",
        ).pack(side="left", padx=16)

        self.status_label = ctk.CTkLabel(header, text="Idle", text_color="#7CFC98")
        self.status_label.pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=8)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, width=280)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        left.grid_propagate(False)

        ctk.CTkLabel(left, text="Systems", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(8, 4))
        self.system_list = ctk.CTkScrollableFrame(left, width=260, height=320)
        self.system_list.pack(fill="both", expand=True, pady=4)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", pady=8)
        ctk.CTkButton(btn_row, text="Add", width=70, command=self._add_system).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Radio Aux", width=90, command=self._add_radio_aux).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Edit", width=70, command=self._edit_system).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Delete", width=70, fg_color="#8B0000", command=self._delete_system).pack(side="left", padx=2)

        ctk.CTkButton(left, text="Start Selected System", command=self._start_selected).pack(fill="x", pady=4)
        ctk.CTkButton(left, text="Start All (Multi-Dongle)", command=self._start_all_multi).pack(fill="x", pady=4)
        ctk.CTkButton(left, text="Trunk Scan All (1 dongle)", fg_color="#555555", command=self._start_trunk_scan).pack(fill="x", pady=4)
        stop_row = ctk.CTkFrame(left, fg_color="transparent")
        stop_row.pack(fill="x", pady=4)
        ctk.CTkButton(stop_row, text="Stop Selected", fg_color="#8B0000", command=self._stop_selected).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(stop_row, text="Stop All", fg_color="#5a0000", command=self._stop).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(left, text="Settings", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(16, 4))
        self.record_var = ctk.BooleanVar(value=self.settings.auto_record)
        ctk.CTkCheckBox(left, text="Record calls (-P)", variable=self.record_var, command=self._save_settings).pack(anchor="w")
        self.enc_var = ctk.BooleanVar(value=self.settings.block_encrypted)
        ctk.CTkCheckBox(left, text="Block encrypted", variable=self.enc_var, command=self._save_settings).pack(anchor="w")
        ctk.CTkButton(left, text="Setup / DSD-neo", fg_color="#444444", command=self._show_setup).pack(fill="x", pady=(12, 0))

        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="Live Activity", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=12, pady=(12, 4))
        self.log_box = ctk.CTkTextbox(right, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log_box.configure(state="disabled")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(0, 12))
        self.decoder_label = ctk.CTkLabel(footer, text="", text_color="#888888", anchor="w")
        self.decoder_label.pack(fill="x")
        self._update_decoder_label()

    def _maybe_show_setup(self) -> None:
        exe = find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)
        if not exe:
            self._show_setup()

    def _show_setup(self) -> None:
        SetupDialog(self, self.store, self.settings, on_complete=self._on_setup_complete)

    def _on_setup_complete(self, settings: AppSettings) -> None:
        self.settings = settings
        self._save_settings()
        self._update_decoder_label()
        devices = list_rtl_devices(Path(self.settings.dsdneo_path))
        if devices:
            self._append_log("RTL devices: " + ", ".join(devices))
        audio = self._audio_devices()
        if len(audio) > 1:
            self._append_log("Line-in devices: " + ", ".join(label for _, label in audio[1:6]))

    def _decoder_exe(self) -> Path | None:
        return find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)

    def _audio_devices(self) -> list[tuple[str, str]]:
        exe = self._decoder_exe()
        if exe:
            return list_audio_devices(exe)
        return [("", "Default input device")]

    def _update_decoder_label(self) -> None:
        exe = find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)
        if not exe:
            self.decoder_label.configure(text="Decoder: not configured")
            return
        ok, msg = verify_dsdneo(exe)
        state = "ready" if ok else "error"
        self.decoder_label.configure(text=f"Decoder: {exe} ({state}) — {msg}")

    def _refresh_system_list(self) -> None:
        for child in self.system_list.winfo_children():
            child.destroy()

        if not self.systems:
            ctk.CTkLabel(self.system_list, text="No systems configured.\nClick Add to create one.", text_color="#888888").pack(pady=20)
            return

        for index, system in enumerate(self.systems):
            label = PROTOCOL_LABELS.get(system.protocol, system.protocol.value)
            if system.input_source == InputSource.LINE_IN:
                source = "Radio aux / line-in"
            else:
                freq = system.control_frequency_hz / 1_000_000
                source = f"Dongle #{system.rtl_device} · {freq:.4f} MHz"
            active = system.name in self.engine.active_session_names
            prefix = "▶ " if active else ""
            text = f"{prefix}{system.name}\n{label} · {source}"
            btn = ctk.CTkButton(
                self.system_list,
                text=text,
                anchor="w",
                fg_color="#1f538d" if index == self.selected_index else ("#2d5a27" if active else "#333333"),
                hover_color="#444444",
                command=lambda i=index: self._select_system(i),
            )
            btn.pack(fill="x", pady=3)

    def _select_system(self, index: int) -> None:
        self.selected_index = index
        self._refresh_system_list()

    def _add_system(self) -> None:
        SystemEditor(self, on_save=self._on_system_saved, audio_devices=self._audio_devices())

    def _add_radio_aux(self) -> None:
        preset = ScannerSystem(
            name="Radio Aux",
            protocol=Protocol.AUTO,
            input_source=InputSource.LINE_IN,
            system_type=SystemType.CONVENTIONAL,
            use_trunking=False,
            input_volume=2,
            notes="Baofeng/scanner aux cable to PC line-in or mic",
        )
        SystemEditor(self, system=preset, on_save=self._on_system_saved, audio_devices=self._audio_devices())

    def _edit_system(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Choose a system to edit.")
            return
        SystemEditor(
            self,
            system=self.systems[self.selected_index],
            on_save=self._on_system_saved,
            audio_devices=self._audio_devices(),
        )

    def _delete_system(self) -> None:
        if self.selected_index is None:
            return
        if messagebox.askyesno("Delete system", f"Delete '{self.systems[self.selected_index].name}'?"):
            del self.systems[self.selected_index]
            self.selected_index = None
            self._save_settings()
            self._refresh_system_list()

    def _on_system_saved(self, system: ScannerSystem) -> None:
        if self.selected_index is not None and self.selected_index < len(self.systems):
            self.systems[self.selected_index] = system
        else:
            self.systems.append(system)
            self.selected_index = len(self.systems) - 1
        self._save_settings()
        self._refresh_system_list()

    def _save_settings(self) -> None:
        self.settings.auto_record = self.record_var.get()
        self.settings.block_encrypted = self.enc_var.get()
        self.store.save(self.settings, self.systems)

    def _get_decoder(self) -> Path | None:
        exe = find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)
        if not exe:
            messagebox.showerror("Decoder missing", "Install DSD-neo from Setup first.")
            return None
        ok, msg = verify_dsdneo(exe)
        if not ok:
            messagebox.showerror("Decoder error", msg)
            return None
        return exe

    def _recordings_dir(self) -> Path:
        recordings = Path(self.settings.recordings_dir)
        if not recordings.is_absolute():
            recordings = self.store.base_dir / recordings
        recordings.mkdir(parents=True, exist_ok=True)
        return recordings

    def _update_status(self) -> None:
        names = [n for n in self.engine.active_session_names if n != "__trunk_scan__"]
        if not names:
            self.status_label.configure(text="Idle", text_color="#aaaaaa")
        elif len(names) == 1:
            self.status_label.configure(text=f"Monitoring: {names[0]}", text_color="#7CFC98")
        else:
            self.status_label.configure(text=f"Multi-dongle: {len(names)} systems active", text_color="#7CFC98")
        self._refresh_system_list()

    def _start_selected(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Choose a system to monitor.")
            return
        exe = self._get_decoder()
        if not exe:
            return

        system = self.systems[self.selected_index]
        runtime = self.store.system_runtime_dir(system.name)

        try:
            command = self.engine.start_system(
                exe,
                system,
                self.settings,
                runtime,
                self._recordings_dir(),
                stop_others=False,
            )
            self.engine.register_system_meta(system.name, system)
        except ValueError as exc:
            messagebox.showerror("Cannot start", str(exc))
            return

        self._append_log(f"[{system.name}] Started decoder")
        self._append_log(" ".join(command))
        self._update_status()

    def _start_all_multi(self) -> None:
        rtl_systems = [s for s in self.systems if s.input_source == InputSource.RTL_SDR]
        if len(rtl_systems) < 2:
            messagebox.showinfo(
                "Multi-dongle",
                "Add at least two RTL-SDR systems with different dongle device indices (0, 1, 2, ...).",
            )
            return

        exe = self._get_decoder()
        if not exe:
            return

        runtime_root = self.store.runtime_dir / "multi_dongle"
        try:
            commands = self.engine.start_all_systems(
                exe,
                self.systems,
                self.settings,
                runtime_root,
                self._recordings_dir(),
            )
        except ValueError as exc:
            messagebox.showerror("Cannot start multi-dongle", str(exc))
            return

        for system, command in zip(rtl_systems, commands):
            self.engine.register_system_meta(system.name, system)
            self._append_log(f"[{system.name}] Started on dongle #{system.rtl_device}")
            self._append_log(" ".join(command))

        self._update_status()

    def _start_trunk_scan(self) -> None:
        if len(self.systems) < 2:
            messagebox.showinfo("Trunk scan", "Add at least two RTL-SDR systems for single-dongle trunk scan rotation.")
            return
        if any(system.input_source == InputSource.LINE_IN for system in self.systems):
            messagebox.showinfo("Trunk scan", "Trunk scan requires RTL-SDR input. Line-in/radio aux systems are excluded.")
            return
        exe = self._get_decoder()
        if not exe:
            return

        runtime = self.store.runtime_dir / "trunk_scan"
        command = self.engine.start_trunk_scan(exe, self.systems, self.settings, runtime, self._recordings_dir())
        self._append_log("Started trunk scan")
        self._append_log(" ".join(command))
        self._update_status()

    def _stop_selected(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Choose a system to stop.")
            return
        name = self.systems[self.selected_index].name
        self.engine.stop_session(name)
        self._append_log(f"[{name}] Stop requested")
        self._update_status()

    def _stop(self) -> None:
        self.engine.stop()
        self._append_log("Stopped all decoders")
        self._update_status()

    def _append_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll_events(self) -> None:
        while True:
            try:
                item = self.engine.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, CallEvent):
                prefix = f"[{item.session}] " if item.session else ""
                parts = [f"{prefix}{item.text}"]
                if item.talkgroup:
                    parts.append(f"TG {item.talkgroup}")
                self._append_log(" | ".join(parts))
            else:
                self._append_log(str(item))
                if "Decoder stopped" in str(item):
                    self._update_status()
        self.after(300, self._poll_events)

    def _on_close(self) -> None:
        self.engine.stop()
        self._save_settings()
        self.destroy()


def run_app() -> None:
    app = MainWindow()
    app.mainloop()
