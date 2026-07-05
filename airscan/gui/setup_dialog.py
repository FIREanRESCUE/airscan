from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox

from airscan.config_store import ConfigStore
from airscan.dsdneo_setup import download_dsdneo, find_dsdneo, verify_dsdneo
from airscan.models import AppSettings
from airscan.gui.theme import ACCENT, BG, FONT_BODY, FONT_HEADING, FONT_SMALL, PAD, PANEL, SUCCESS, TEXT, TEXT_MUTED
from airscan.gui.widgets import ghost_button, muted_label, primary_button, section_label


class SetupDialog(ctk.CTkToplevel):
    def __init__(self, master, store: ConfigStore, settings: AppSettings, on_complete) -> None:
        super().__init__(master)
        self.store = store
        self.settings = settings
        self.on_complete = on_complete

        self.title("Setup AirScan")
        self.geometry("520x400")
        self.configure(fg_color=BG)
        self.grab_set()

        body = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
        body.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        section_label(body, "Welcome to AirScan")
        muted_label(
            body,
            "AirScan needs the DSD-neo decoder and an RTL-SDR dongle with the WinUSB driver (install via Zadig).",
            wrap=440,
        )

        self.status = ctk.CTkLabel(body, text="Checking decoder...", font=FONT_SMALL, text_color=TEXT_MUTED)
        self.status.pack(fill="x", pady=(8, 12))

        self.progress = ctk.CTkProgressBar(body, width=420, progress_color=ACCENT)
        self.progress.pack(pady=(0, 16))
        self.progress.set(0)

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        ghost_button(row, "Download DSD-neo", self._download).pack(side="left", padx=(0, 8))
        ghost_button(row, "Browse...", self._browse).pack(side="left", padx=(0, 8))
        primary_button(row, "Continue", self._continue).pack(side="right")

        self.after(200, self._refresh_status)

    def _refresh_status(self) -> None:
        exe = find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)
        if not exe:
            self.status.configure(text="Decoder not installed yet.", text_color=TEXT_MUTED)
            return
        ok, message = verify_dsdneo(exe)
        color = SUCCESS if ok else "#FF8A80"
        self.status.configure(text=f"{'Ready' if ok else 'Problem'}: {message}", text_color=color)
        if ok:
            self.settings.dsdneo_path = str(exe)

    def _download(self) -> None:
        self.status.configure(text="Downloading DSD-neo...", text_color=TEXT_MUTED)
        self.progress.set(0)

        def progress(ratio: float) -> None:
            self.after(0, lambda: self.progress.set(ratio))

        try:
            exe = download_dsdneo(self.store.dsdneo_dir, progress_callback=progress)
            self.settings.dsdneo_path = str(exe)
            self.progress.set(1)
            self._refresh_status()
        except Exception as exc:
            messagebox.showerror("Download failed", str(exc), parent=self)

    def _browse(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self,
            title="Select dsd-neo.exe",
            filetypes=[("DSD-neo", "dsd-neo.exe"), ("Executables", "*.exe")],
        )
        if path:
            self.settings.dsdneo_path = path
            self._refresh_status()

    def _continue(self) -> None:
        exe = find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)
        if not exe:
            messagebox.showwarning("Almost there", "Download or locate DSD-neo first.", parent=self)
            return
        ok, _ = verify_dsdneo(exe)
        if not ok:
            messagebox.showwarning("Decoder issue", "DSD-neo could not be verified.", parent=self)
            return
        self.settings.dsdneo_path = str(exe)
        self.on_complete(self.settings)
        self.destroy()
