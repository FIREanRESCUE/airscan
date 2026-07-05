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
from airscan.gui.theme import (
    ACCENT,
    BG,
    BORDER,
    FONT_BODY,
    FONT_HEADING,
    FONT_MONO,
    FONT_SMALL,
    FONT_TITLE,
    PAD,
    PANEL,
    SUCCESS,
    TEXT,
    TEXT_MUTED,
)
from airscan.gui.widgets import (
    SystemCard,
    danger_button,
    ghost_button,
    muted_label,
    primary_button,
    protocol_color,
    section_label,
)
from airscan.models import AppSettings, InputSource, Protocol, ScannerSystem, SystemType


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=BG)

        self.store = ConfigStore()
        self.settings, self.systems = self.store.load()
        self.engine = DsdNeoEngine()
        self.selected_index: int | None = None

        self.title("AirScan")
        self.geometry("1180x760")
        self.minsize(960, 640)

        self._build_layout()
        self._refresh_system_list()
        self.after(300, self._poll_events)
        self.after(500, self._maybe_show_setup)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        top = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=64)
        top.pack(fill="x")
        top.pack_propagate(False)

        brand = ctk.CTkFrame(top, fg_color="transparent")
        brand.pack(side="left", padx=PAD, pady=12)
        ctk.CTkLabel(brand, text="AirScan", font=FONT_TITLE, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(brand, text="Digital radio scanner", font=FONT_SMALL, text_color=TEXT_MUTED).pack(side="left", padx=(12, 0))

        self.status_pill = ctk.CTkLabel(top, text="● Idle", font=FONT_BODY, text_color=TEXT_MUTED)
        self.status_pill.pack(side="right", padx=(0, PAD))

        ghost_button(top, "Setup", self._show_setup, width=80).pack(side="right", padx=(0, 8), pady=12)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=12, width=360)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, PAD))
        left.grid_propagate(False)

        header = ctk.CTkFrame(left, fg_color="transparent")
        header.pack(fill="x", padx=PAD, pady=(PAD, 8))
        section_label(header, "Systems")
        ghost_button(header, "+ New", self._add_system, width=70).pack(side="right")

        self.system_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.system_list.pack(fill="both", expand=True, padx=PAD, pady=(0, 8))

        actions = ctk.CTkFrame(left, fg_color="transparent")
        actions.pack(fill="x", padx=PAD, pady=(0, PAD))
        self.start_btn = primary_button(actions, "Start Selected", self._start_selected)
        self.start_btn.pack(fill="x", pady=(0, 8))
        self.start_all_btn = ghost_button(actions, "Start All Dongles", self._start_all_multi)
        self.start_all_btn.pack(fill="x", pady=(0, 8))
        stop_row = ctk.CTkFrame(actions, fg_color="transparent")
        stop_row.pack(fill="x")
        danger_button(stop_row, "Stop All", self._stop).pack(side="right")
        ghost_button(stop_row, "Stop Selected", self._stop_selected).pack(side="right", padx=(0, 8))

        more = ctk.CTkFrame(left, fg_color="transparent")
        more.pack(fill="x", padx=PAD, pady=(0, 4))
        ghost_button(more, "Delete Selected", self._delete_selected).pack(side="left")
        ghost_button(more, "Single-Dongle Scan", self._start_trunk_scan).pack(side="right")

        options = ctk.CTkFrame(left, fg_color=BG, corner_radius=10)
        options.pack(fill="x", padx=PAD, pady=(0, PAD))
        self.record_var = ctk.BooleanVar(value=self.settings.auto_record)
        self.enc_var = ctk.BooleanVar(value=self.settings.block_encrypted)
        ctk.CTkCheckBox(options, text="Record calls", variable=self.record_var, command=self._save_settings, font=FONT_SMALL).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkCheckBox(options, text="Block encrypted", variable=self.enc_var, command=self._save_settings, font=FONT_SMALL).pack(anchor="w", padx=12, pady=(0, 10))

        right = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(right, fg_color="transparent")
        log_header.pack(fill="x", padx=PAD, pady=(PAD, 8))
        section_label(log_header, "Live Activity")
        ghost_button(log_header, "Clear", self._clear_log, width=70).pack(side="right")

        self.log_box = ctk.CTkTextbox(right, font=FONT_MONO, fg_color=BG, border_color=BORDER, text_color=TEXT)
        self.log_box.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.log_box.configure(state="disabled")

        self.decoder_label = ctk.CTkLabel(self, text="", font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w")
        self.decoder_label.pack(fill="x", padx=PAD, pady=(0, 8))
        self._update_decoder_label()

    def _maybe_show_setup(self) -> None:
        if not find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir):
            self._show_setup()

    def _show_setup(self) -> None:
        SetupDialog(self, self.store, self.settings, on_complete=self._on_setup_complete)

    def _on_setup_complete(self, settings: AppSettings) -> None:
        self.settings = settings
        self._save_settings()
        self._update_decoder_label()
        rtl = list_rtl_devices(Path(self.settings.dsdneo_path))
        if rtl:
            self._append_log("RTL-SDR devices detected.")

    def _decoder_exe(self) -> Path | None:
        return find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)

    def _audio_devices(self) -> list[tuple[str, str]]:
        exe = self._decoder_exe()
        return list_audio_devices(exe) if exe else [("", "Default input device")]

    def _update_decoder_label(self) -> None:
        exe = self._decoder_exe()
        if not exe:
            self.decoder_label.configure(text="Decoder not configured — open Setup")
            return
        ok, _ = verify_dsdneo(exe)
        self.decoder_label.configure(text=f"Decoder: {'ready' if ok else 'error'}")

    def _system_subtitle(self, system: ScannerSystem) -> str:
        if system.input_source == InputSource.LINE_IN:
            return "Radio aux input"
        mhz = system.control_frequency_hz / 1_000_000
        return f"Dongle {system.rtl_device} · {mhz:.4f} MHz"

    def _refresh_system_list(self) -> None:
        for child in self.system_list.winfo_children():
            child.destroy()

        if not self.systems:
            empty = ctk.CTkFrame(self.system_list, fg_color=BG, corner_radius=10)
            empty.pack(fill="x", pady=8)
            ctk.CTkLabel(empty, text="No systems yet", font=FONT_BODY, text_color=TEXT).pack(pady=(16, 4))
            muted_label(empty, "Add a system to monitor P25, DMR, or NXDN.", wrap=280)
            primary_button(empty, "Create First System", self._add_system).pack(pady=(4, 16), padx=16, fill="x")
            return

        for index, system in enumerate(self.systems):
            badge = PROTOCOL_LABELS.get(system.protocol, "Radio")
            if system.input_source == InputSource.LINE_IN:
                badge = "Aux In"
            card = SystemCard(
                self.system_list,
                name=system.name,
                subtitle=self._system_subtitle(system),
                badge=badge,
                badge_color=protocol_color(system.protocol.value, system.input_source == InputSource.LINE_IN),
                selected=index == self.selected_index,
                active=system.name in self.engine.active_session_names,
                on_select=lambda i=index: self._select_system(i),
                on_start=lambda i=index: self._start_system_at(i),
                on_edit=lambda i=index: self._edit_system_at(i),
            )
            card.pack(fill="x", pady=6)

        rtl_count = sum(1 for s in self.systems if s.input_source == InputSource.RTL_SDR)
        if rtl_count >= 2:
            self.start_all_btn.configure(state="normal")
        else:
            self.start_all_btn.configure(state="disabled")

    def _select_system(self, index: int) -> None:
        self.selected_index = index
        self._refresh_system_list()

    def _add_system(self) -> None:
        SystemEditor(self, on_save=self._on_system_saved, audio_devices=self._audio_devices())

    def _edit_system_at(self, index: int) -> None:
        self.selected_index = index
        SystemEditor(self, system=self.systems[index], on_save=self._on_system_saved, audio_devices=self._audio_devices())

    def _edit_system(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Click a system card first.")
            return
        self._edit_system_at(self.selected_index)

    def _delete_selected(self) -> None:
        if self.selected_index is None:
            return
        name = self.systems[self.selected_index].name
        if messagebox.askyesno("Delete system", f"Delete '{name}'?"):
            self.engine.stop_session(name)
            del self.systems[self.selected_index]
            self.selected_index = None
            self._save_settings()
            self._refresh_system_list()
            self._update_status()

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
        exe = self._decoder_exe()
        if not exe:
            messagebox.showerror("Setup required", "Install DSD-neo from Setup first.")
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
            self.status_pill.configure(text="● Idle", text_color=TEXT_MUTED)
        elif len(names) == 1:
            self.status_pill.configure(text=f"● {names[0]}", text_color=SUCCESS)
        else:
            self.status_pill.configure(text=f"● {len(names)} systems live", text_color=SUCCESS)
        self._refresh_system_list()

    def _start_system_at(self, index: int) -> None:
        self.selected_index = index
        self._start_selected()

    def _start_selected(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Click a system card first.")
            return
        exe = self._get_decoder()
        if not exe:
            return

        system = self.systems[self.selected_index]
        try:
            self.engine.start_system(
                exe,
                system,
                self.settings,
                self.store.system_runtime_dir(system.name),
                self._recordings_dir(),
                stop_others=False,
            )
            self.engine.register_system_meta(system.name, system)
        except ValueError as exc:
            messagebox.showerror("Cannot start", str(exc))
            return

        self._append_log(f"[{system.name}] Started")
        self._update_status()

    def _start_all_multi(self) -> None:
        rtl_systems = [s for s in self.systems if s.input_source == InputSource.RTL_SDR]
        if len(rtl_systems) < 2:
            messagebox.showinfo("Need two dongles", "Add at least two systems with different dongle numbers.")
            return
        exe = self._get_decoder()
        if not exe:
            return

        try:
            self.engine.start_all_systems(
                exe,
                self.systems,
                self.settings,
                self.store.runtime_dir / "multi_dongle",
                self._recordings_dir(),
            )
        except ValueError as exc:
            messagebox.showerror("Cannot start", str(exc))
            return

        for system in rtl_systems:
            self.engine.register_system_meta(system.name, system)
            self._append_log(f"[{system.name}] Started on dongle {system.rtl_device}")
        self._update_status()

    def _start_trunk_scan(self) -> None:
        if len(self.systems) < 2:
            messagebox.showinfo("Need more systems", "Add at least two RTL-SDR systems for rotation scan.")
            return
        if any(s.input_source == InputSource.LINE_IN for s in self.systems):
            messagebox.showinfo("RTL-SDR only", "Single-dongle scan works with RTL-SDR systems only.")
            return
        exe = self._get_decoder()
        if not exe:
            return
        runtime = self.store.runtime_dir / "trunk_scan"
        self.engine.start_trunk_scan(exe, self.systems, self.settings, runtime, self._recordings_dir())
        self._append_log("Single-dongle scan started")
        self._update_status()

    def _stop_selected(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Click a system card first.")
            return
        name = self.systems[self.selected_index].name
        self.engine.stop_session(name)
        self._append_log(f"[{name}] Stopped")
        self._update_status()

    def _stop(self) -> None:
        self.engine.stop()
        self._append_log("All systems stopped")
        self._update_status()

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

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
                line = item.text
                if item.talkgroup:
                    line += f"  · TG {item.talkgroup}"
                if item.session:
                    line = f"[{item.session}] {line}"
                self._append_log(line)
            else:
                text = str(item)
                if text.startswith("["):
                    self._append_log(text)
                elif "Starting:" not in text:
                    self._append_log(text)
                if "Decoder stopped" in text:
                    self._update_status()
        self.after(300, self._poll_events)

    def _on_close(self) -> None:
        self.engine.stop()
        self._save_settings()
        self.destroy()


def run_app() -> None:
    app = MainWindow()
    app.mainloop()
