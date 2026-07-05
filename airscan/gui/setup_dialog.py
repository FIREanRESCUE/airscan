from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox

from airscan.config_store import ConfigStore
from airscan.dsdneo_setup import download_dsdneo, find_dsdneo, verify_dsdneo
from airscan.models import AppSettings


class SetupDialog(ctk.CTkToplevel):
    def __init__(self, master, store: ConfigStore, settings: AppSettings, on_complete) -> None:
        super().__init__(master)
        self.store = store
        self.settings = settings
        self.on_complete = on_complete

        self.title("AirScan Setup")
        self.geometry("640x420")
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="First-time setup",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(20, 8))

        ctk.CTkLabel(
            self,
            text=(
                "AirScan uses DSD-neo to decode P25, DMR, and NXDN with trunking support.\n"
                "You also need an RTL-SDR dongle with the WinUSB driver (install via Zadig)."
            ),
            justify="left",
        ).pack(padx=20, pady=8)

        self.status = ctk.CTkLabel(self, text="Checking decoder...", text_color="#cccccc")
        self.status.pack(pady=8)

        self.progress = ctk.CTkProgressBar(self, width=420)
        self.progress.pack(pady=8)
        self.progress.set(0)

        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(pady=16)

        ctk.CTkButton(button_row, text="Download DSD-neo", command=self._download).pack(side="left", padx=8)
        ctk.CTkButton(button_row, text="Browse for dsd-neo.exe", command=self._browse).pack(side="left", padx=8)
        ctk.CTkButton(button_row, text="Continue", command=self._continue).pack(side="left", padx=8)

        self.after(200, self._refresh_status)

    def _refresh_status(self) -> None:
        exe = find_dsdneo(self.settings.dsdneo_path, self.store.dsdneo_dir)
        if not exe:
            self.status.configure(text="DSD-neo not found. Download it or browse to an existing install.")
            return
        ok, message = verify_dsdneo(exe)
        color = "#7CFC98" if ok else "#FF8A80"
        self.status.configure(text=f"{exe}\n{message}", text_color=color)
        if ok:
            self.settings.dsdneo_path = str(exe)

    def _download(self) -> None:
        self.status.configure(text="Downloading DSD-neo...", text_color="#cccccc")
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
            messagebox.showwarning("Setup incomplete", "Install or locate DSD-neo before continuing.", parent=self)
            return
        ok, _ = verify_dsdneo(exe)
        if not ok:
            messagebox.showwarning("Setup incomplete", "DSD-neo could not be verified.", parent=self)
            return
        self.settings.dsdneo_path = str(exe)
        self.on_complete(self.settings)
        self.destroy()
