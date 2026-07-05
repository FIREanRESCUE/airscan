from __future__ import annotations

import customtkinter as ctk

from airscan.models import ChannelEntry, Protocol, ScannerSystem, SystemType, Talkgroup


PROTOCOL_LABELS = {
    Protocol.P25_TRUNK: "P25 Trunk (Phase 1/2 auto)",
    Protocol.P25_PHASE1: "P25 Phase 1",
    Protocol.P25_PHASE2: "P25 Phase 2",
    Protocol.DMR_TRUNK: "DMR Trunk (Tier III / Cap+ / Con+)",
    Protocol.DMR_CONVENTIONAL: "DMR Conventional",
    Protocol.NXDN48: "NXDN 6.25 kHz (Type-C/D)",
    Protocol.NXDN96: "NXDN 12.5 kHz",
    Protocol.AUTO: "Auto-detect",
}


class SystemEditor(ctk.CTkToplevel):
    def __init__(self, master, system: ScannerSystem | None = None, on_save=None) -> None:
        super().__init__(master)
        self.on_save = on_save
        self.system = system or ScannerSystem(name="New System", protocol=Protocol.P25_TRUNK)

        self.title("System Editor")
        self.geometry("760x680")
        self.grab_set()

        form = ctk.CTkScrollableFrame(self)
        form.pack(fill="both", expand=True, padx=16, pady=16)

        self.name_var = ctk.StringVar(value=self.system.name)
        self.protocol_var = ctk.StringVar(value=self.system.protocol.value)
        self.freq_var = ctk.StringVar(value=f"{self.system.control_frequency_hz / 1_000_000:.6f}")
        self.device_var = ctk.StringVar(value=str(self.system.rtl_device))
        self.gain_var = ctk.StringVar(value=str(self.system.gain))
        self.ppm_var = ctk.StringVar(value=str(self.system.ppm))
        self.bw_var = ctk.StringVar(value=str(self.system.bandwidth))
        self.mod_var = ctk.StringVar(value=self.system.modulation)
        self.trunk_var = ctk.BooleanVar(value=self.system.use_trunking)
        self.whitelist_var = ctk.BooleanVar(value=self.system.use_whitelist)
        self.notes_var = ctk.StringVar(value=self.system.notes)

        self._field(form, "System name", self.name_var)
        self._combo(form, "Protocol", self.protocol_var, [p.value for p in Protocol], PROTOCOL_LABELS)
        self._field(form, "Control frequency (MHz)", self.freq_var)
        self._field(form, "RTL-SDR device index", self.device_var)
        self._field(form, "Gain (0=auto, 1-49 manual dB)", self.gain_var)
        self._field(form, "PPM correction", self.ppm_var)
        self._field(form, "Bandwidth (MHz)", self.bw_var)
        self._combo(form, "Modulation", self.mod_var, ["auto", "c4fm", "cqpsk", "gfsk"])
        ctk.CTkCheckBox(form, text="Enable trunking follow (-T)", variable=self.trunk_var).pack(anchor="w", pady=4)
        ctk.CTkCheckBox(form, text="Use talkgroup whitelist (-W)", variable=self.whitelist_var).pack(anchor="w", pady=4)
        self._field(form, "Notes", self.notes_var)

        ctk.CTkLabel(form, text="Channel map (channel,frequency_mhz,note — one per line)", anchor="w").pack(fill="x", pady=(12, 4))
        self.channels_text = ctk.CTkTextbox(form, height=120)
        self.channels_text.pack(fill="x", pady=4)
        self.channels_text.insert("1.0", self._channels_to_text())

        ctk.CTkLabel(form, text="Talkgroups (id,mode,name — one per line)", anchor="w").pack(fill="x", pady=(12, 4))
        self.talkgroups_text = ctk.CTkTextbox(form, height=120)
        self.talkgroups_text.pack(fill="x", pady=4)
        self.talkgroups_text.insert("1.0", self._talkgroups_to_text())

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(buttons, text="Save", command=self._save).pack(side="right", padx=6)
        ctk.CTkButton(buttons, text="Cancel", fg_color="#444444", command=self.destroy).pack(side="right")

    def _field(self, parent, label: str, variable) -> None:
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", pady=(8, 2))
        ctk.CTkEntry(parent, textvariable=variable).pack(fill="x")

    def _combo(self, parent, label: str, variable, values: list[str], labels: dict | None = None) -> None:
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", pady=(8, 2))
        display = [labels.get(v, v) if labels else v for v in values]
        combo = ctk.CTkComboBox(parent, values=display, command=lambda _choice: None)
        current = labels.get(variable.get(), variable.get()) if labels else variable.get()
        combo.set(current)
        combo.configure(command=lambda choice: variable.set(values[display.index(choice)]))
        combo.pack(fill="x")

    def _channels_to_text(self) -> str:
        lines = []
        for channel in self.system.channels:
            mhz = channel.frequency_hz / 1_000_000
            suffix = f",{channel.note}" if channel.note else ""
            lines.append(f"{channel.channel_number},{mhz:.6f}{suffix}")
        return "\n".join(lines)

    def _talkgroups_to_text(self) -> str:
        lines = []
        for tg in self.system.talkgroups:
            lines.append(f"{tg.talkgroup_id},{tg.mode},{tg.name}")
        return "\n".join(lines)

    def _parse_channels(self) -> list[ChannelEntry]:
        entries: list[ChannelEntry] = []
        for raw in self.channels_text.get("1.0", "end").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2:
                continue
            freq_mhz = float(parts[1])
            entries.append(
                ChannelEntry(
                    channel_number=int(parts[0]),
                    frequency_hz=int(freq_mhz * 1_000_000),
                    note=parts[2] if len(parts) > 2 else "",
                )
            )
        return entries

    def _parse_talkgroups(self) -> list[Talkgroup]:
        entries: list[Talkgroup] = []
        for raw in self.talkgroups_text.get("1.0", "end").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 3:
                continue
            entries.append(
                Talkgroup(
                    talkgroup_id=int(parts[0]),
                    mode=parts[1],
                    name=parts[2],
                    tag=parts[3] if len(parts) > 3 else "",
                )
            )
        return entries

    def _save(self) -> None:
        try:
            system = ScannerSystem(
                name=self.name_var.get().strip() or "Unnamed System",
                protocol=Protocol(self.protocol_var.get()),
                system_type=SystemType.TRUNKED if self.trunk_var.get() else SystemType.CONVENTIONAL,
                control_frequency_hz=int(float(self.freq_var.get()) * 1_000_000),
                channels=self._parse_channels(),
                talkgroups=self._parse_talkgroups(),
                rtl_device=int(self.device_var.get()),
                gain=int(self.gain_var.get()),
                ppm=int(self.ppm_var.get()),
                bandwidth=int(float(self.bw_var.get())),
                use_trunking=self.trunk_var.get(),
                use_whitelist=self.whitelist_var.get(),
                modulation=self.mod_var.get(),
                notes=self.notes_var.get().strip(),
            )
        except ValueError as exc:
            ctk.CTkLabel(self, text=f"Invalid input: {exc}", text_color="#FF8A80").pack()
            return

        if self.on_save:
            self.on_save(system)
        self.destroy()
