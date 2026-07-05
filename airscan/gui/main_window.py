from __future__ import annotations

import queue
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from airscan.config_store import ConfigStore
from airscan.dsdneo_engine import CallEvent, DsdNeoEngine
from airscan.dsdneo_setup import find_dsdneo, list_rtl_devices, verify_dsdneo
from airscan.gui.setup_dialog import SetupDialog
from airscan.gui.system_editor import PROTOCOL_LABELS, SystemEditor
from airscan.models import AppSettings, Protocol, ScannerSystem


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.store = ConfigStore()
        self.settings, self.systems = self.store.load()
        self.engine = DsdNeoEngine()
        self.selected_index: int | None = None

        self.title("AirScan — Multi-Protocol RTL-SDR Scanner")
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
            text="P25 · DMR · NXDN trunking for RTL-SDR",
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
        ctk.CTkButton(btn_row, text="Edit", width=70, command=self._edit_system).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Delete", width=70, fg_color="#8B0000", command=self._delete_system).pack(side="left", padx=2)

        ctk.CTkButton(left, text="Start Selected System", command=self._start_selected).pack(fill="x", pady=4)
        ctk.CTkButton(left, text="Trunk Scan All (1 dongle)", fg_color="#555555", command=self._start_trunk_scan).pack(fill="x", pady=4)
        ctk.CTkButton(left, text="Stop", fg_color="#8B0000", command=self._stop).pack(fill="x", pady=4)

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
            self._append_log("Detected devices: " + ", ".join(devices))

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
            freq = system.control_frequency_hz / 1_000_000
            text = f"{system.name}\n{label} · {freq:.4f} MHz"
            btn = ctk.CTkButton(
                self.system_list,
                text=text,
                anchor="w",
                fg_color="#333333" if index != self.selected_index else "#1f538d",
                hover_color="#444444",
                command=lambda i=index: self._select_system(i),
            )
            btn.pack(fill="x", pady=3)

    def _select_system(self, index: int) -> None:
        self.selected_index = index
        self._refresh_system_list()

    def _add_system(self) -> None:
        SystemEditor(self, on_save=self._on_system_saved)

    def _edit_system(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Choose a system to edit.")
            return
        SystemEditor(self, system=self.systems[self.selected_index], on_save=self._on_system_saved)

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

    def _start_selected(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Select a system", "Choose a system to monitor.")
            return
        exe = self._get_decoder()
        if not exe:
            return

        system = self.systems[self.selected_index]
        runtime = self.store.system_runtime_dir(system.name)
        recordings = Path(self.settings.recordings_dir)
        if not recordings.is_absolute():
            recordings = self.store.base_dir / recordings

        command = self.engine.start_system(exe, system, self.settings, runtime, recordings)
        self.status_label.configure(text=f"Monitoring: {system.name}", text_color="#7CFC98")
        self._append_log("Started decoder")
        self._append_log(" ".join(command))

    def _start_trunk_scan(self) -> None:
        if len(self.systems) < 2:
            messagebox.showinfo("Trunk scan", "Add at least two systems for single-dongle trunk scan rotation.")
            return
        exe = self._get_decoder()
        if not exe:
            return

        runtime = self.store.runtime_dir / "trunk_scan"
        recordings = Path(self.settings.recordings_dir)
        if not recordings.is_absolute():
            recordings = self.store.base_dir / recordings

        command = self.engine.start_trunk_scan(exe, self.systems, self.settings, runtime, recordings)
        self.status_label.configure(text="Trunk scan active", text_color="#7CFC98")
        self._append_log("Started trunk scan")
        self._append_log(" ".join(command))

    def _stop(self) -> None:
        self.engine.stop()
        self.status_label.configure(text="Idle", text_color="#aaaaaa")
        self._append_log("Stopped decoder")

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
                parts = [item.text]
                if item.talkgroup:
                    parts.append(f"TG {item.talkgroup}")
                self._append_log(" | ".join(parts))
            else:
                self._append_log(str(item))
                if str(item).startswith("Decoder stopped"):
                    self.status_label.configure(text="Idle", text_color="#aaaaaa")
        self.after(300, self._poll_events)

    def _on_close(self) -> None:
        self.engine.stop()
        self._save_settings()
        self.destroy()


def run_app() -> None:
    app = MainWindow()
    app.mainloop()
