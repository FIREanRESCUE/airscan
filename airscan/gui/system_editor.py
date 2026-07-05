from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox

from airscan.models import ChannelEntry, InputSource, Protocol, ScannerSystem, SystemType, Talkgroup
from airscan.gui.theme import (
    ACCENT,
    BG,
    BORDER,
    FONT_BODY,
    FONT_HEADING,
    FONT_SMALL,
    PAD,
    PANEL,
    TEXT,
    TEXT_MUTED,
)
from airscan.gui.widgets import ghost_button, muted_label, primary_button, protocol_color, section_label


PROTOCOL_LABELS = {
    Protocol.P25_TRUNK: "P25 Trunk",
    Protocol.P25_PHASE1: "P25 Phase 1",
    Protocol.P25_PHASE2: "P25 Phase 2",
    Protocol.DMR_TRUNK: "DMR Trunk",
    Protocol.DMR_CONVENTIONAL: "DMR",
    Protocol.NXDN48: "NXDN 6.25",
    Protocol.NXDN96: "NXDN 12.5",
    Protocol.AUTO: "Auto",
}

INPUT_LABELS = {
    InputSource.RTL_SDR: "RTL-SDR dongle",
    InputSource.LINE_IN: "Radio aux / line-in",
}

PRESETS = {
    "P25 Trunk": ScannerSystem(name="P25 System", protocol=Protocol.P25_TRUNK, use_trunking=True),
    "DMR Trunk": ScannerSystem(name="DMR System", protocol=Protocol.DMR_TRUNK, use_trunking=True),
    "NXDN": ScannerSystem(name="NXDN System", protocol=Protocol.NXDN96, use_trunking=True),
    "Radio Aux": ScannerSystem(
        name="Radio Aux",
        protocol=Protocol.AUTO,
        input_source=InputSource.LINE_IN,
        system_type=SystemType.CONVENTIONAL,
        use_trunking=False,
        input_volume=2,
    ),
}


class SystemEditor(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        system: ScannerSystem | None = None,
        on_save=None,
        audio_devices: list[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_save = on_save
        self.audio_devices = audio_devices or [("", "Default input device")]
        self.system = system or ScannerSystem(name="New System", protocol=Protocol.P25_TRUNK)

        self.title("Configure System")
        self.geometry("720x680")
        self.configure(fg_color=BG)
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PAD, pady=(PAD, 0))
        section_label(header, "Configure System")
        muted_label(header, "Set the protocol, input source, and trunking details for this system.", wrap=660)

        if self.system.name == "New System":
            presets = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=10)
            presets.pack(fill="x", padx=PAD, pady=(0, PAD))
            ctk.CTkLabel(presets, text="Quick start", font=FONT_SMALL, text_color=TEXT_MUTED).pack(anchor="w", padx=12, pady=(10, 6))
            row = ctk.CTkFrame(presets, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(0, 12))
            for label, preset in PRESETS.items():
                ghost_button(row, label, lambda p=preset: self._apply_preset(p)).pack(side="left", padx=(0, 8))

        self.tabs = ctk.CTkTabview(self, fg_color=PANEL, segmented_button_fg_color=PANEL, segmented_button_selected_color=ACCENT)
        self.tabs.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.tabs.add("Basics")
        self.tabs.add("Trunking")
        self.tabs.add("Advanced")

        self._init_vars()
        self._build_basics(self.tabs.tab("Basics"))
        self._build_trunking(self.tabs.tab("Trunking"))
        self._build_advanced(self.tabs.tab("Advanced"))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=PAD, pady=(0, PAD))
        ghost_button(footer, "Cancel", self.destroy).pack(side="right", padx=(8, 0))
        primary_button(footer, "Save System", self._save).pack(side="right")

        self._toggle_input_sections()

    def _init_vars(self) -> None:
        self.name_var = ctk.StringVar(value=self.system.name)
        self.protocol_var = ctk.StringVar(value=self.system.protocol.value)
        self.input_source_var = ctk.StringVar(value=self.system.input_source.value)
        self.freq_var = ctk.StringVar(value=f"{self.system.control_frequency_hz / 1_000_000:.4f}" if self.system.control_frequency_hz else "")
        self.device_var = ctk.StringVar(value=str(self.system.rtl_device))
        self.audio_device_var = ctk.StringVar(value=self._label_for_device(self.system.audio_device))
        self.input_volume_var = ctk.StringVar(value=str(self.system.input_volume))
        self.rigctl_var = ctk.StringVar(value=str(self.system.rigctl_port or ""))
        self.gain_var = ctk.StringVar(value=str(self.system.gain))
        self.ppm_var = ctk.StringVar(value=str(self.system.ppm))
        self.bw_var = ctk.StringVar(value=str(self.system.bandwidth))
        self.mod_var = ctk.StringVar(value=self.system.modulation)
        self.trunk_var = ctk.BooleanVar(value=self.system.use_trunking)
        self.whitelist_var = ctk.BooleanVar(value=self.system.use_whitelist)
        self.notes_var = ctk.StringVar(value=self.system.notes)

    def _apply_preset(self, preset: ScannerSystem) -> None:
        self.system = preset
        self._init_vars()
        self.name_var.set(preset.name)
        self.protocol_var.set(preset.protocol.value)
        self.input_source_var.set(preset.input_source.value)
        self.trunk_var.set(preset.use_trunking)
        self.input_volume_var.set(str(preset.input_volume))
        self._toggle_input_sections()

    def _build_basics(self, parent) -> None:
        self._field(parent, "Name", self.name_var, "County Fire P25")
        self._combo(parent, "Protocol", self.protocol_var, [p.value for p in Protocol], PROTOCOL_LABELS)
        self._combo(
            parent,
            "Input",
            self.input_source_var,
            [s.value for s in InputSource],
            INPUT_LABELS,
            on_change=self._toggle_input_sections,
        )

        self.rtl_box = ctk.CTkFrame(parent, fg_color="transparent")
        self.rtl_box.pack(fill="x", pady=(8, 0))
        self._field(self.rtl_box, "Control frequency (MHz)", self.freq_var, "851.0125")
        self._field(self.rtl_box, "Dongle number", self.device_var, "0 = first dongle, 1 = second, etc.")

        self.linein_box = ctk.CTkFrame(parent, fg_color="transparent")
        muted_label(
            self.linein_box,
            "Plug the radio earphone jack into your PC mic or line-in. Tune the radio by hand.",
            wrap=620,
        )
        self._combo(self.linein_box, "PC input device", self.audio_device_var, [label for _, label in self.audio_devices])
        self._field(self.linein_box, "Input boost", self.input_volume_var, "Try 2–4 for quiet aux cables")

    def _build_trunking(self, parent) -> None:
        ctk.CTkCheckBox(parent, text="Follow trunked voice automatically", variable=self.trunk_var, font=FONT_BODY).pack(anchor="w", pady=(4, 8))
        ctk.CTkCheckBox(parent, text="Only monitor talkgroups in the list below", variable=self.whitelist_var, font=FONT_BODY).pack(anchor="w", pady=(0, 12))
        muted_label(parent, "Channel map — one line per channel: number,frequency,note", wrap=620)
        self.channels_text = ctk.CTkTextbox(parent, height=130, font=FONT_SMALL, fg_color=BG, border_color=BORDER)
        self.channels_text.pack(fill="x", pady=(0, 12))
        self.channels_text.insert("1.0", self._channels_to_text())
        muted_label(parent, "Talkgroups — one line per group: id,mode,name  (mode A=allow, B=block)", wrap=620)
        self.talkgroups_text = ctk.CTkTextbox(parent, height=130, font=FONT_SMALL, fg_color=BG, border_color=BORDER)
        self.talkgroups_text.pack(fill="x")
        self.talkgroups_text.insert("1.0", self._talkgroups_to_text())

    def _build_advanced(self, parent) -> None:
        muted_label(parent, "These settings are optional. Defaults work for most setups.", wrap=620)
        self._field(parent, "Gain", self.gain_var, "0 = automatic")
        self._field(parent, "PPM correction", self.ppm_var, "Frequency error correction, often -2 to +3")
        self._field(parent, "Bandwidth (MHz)", self.bw_var, "12 is typical")
        self._combo(parent, "Modulation", self.mod_var, ["auto", "c4fm", "cqpsk", "gfsk"])
        self._field(parent, "Rigctl port", self.rigctl_var, "Optional — for SDR++ auto-retune")
        self._field(parent, "Notes", self.notes_var, "")

    def _field(self, parent, label: str, variable, placeholder: str = "") -> None:
        ctk.CTkLabel(parent, text=label, font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w").pack(fill="x", pady=(10, 2))
        entry = ctk.CTkEntry(parent, textvariable=variable, placeholder_text=placeholder, height=36)
        entry.pack(fill="x")

    def _combo(self, parent, label: str, variable, values: list[str], labels: dict | None = None, on_change=None) -> None:
        ctk.CTkLabel(parent, text=label, font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w").pack(fill="x", pady=(10, 2))
        display = [labels.get(v, v) if labels else v for v in values]
        combo = ctk.CTkComboBox(parent, values=display, height=36, command=lambda _c: None)

        def apply_choice(choice: str) -> None:
            variable.set(values[display.index(choice)])
            if on_change:
                on_change(choice)

        current = labels.get(variable.get(), variable.get()) if labels else variable.get()
        combo.set(current)
        combo.configure(command=apply_choice)
        combo.pack(fill="x")

    def _label_for_device(self, device_id: str) -> str:
        for candidate_id, label in self.audio_devices:
            if candidate_id == device_id:
                return label
        return self.audio_devices[0][1]

    def _device_id_for_label(self, label: str) -> str:
        for candidate_id, candidate_label in self.audio_devices:
            if candidate_label == label:
                return candidate_id
        return ""

    def _toggle_input_sections(self, _choice: str | None = None) -> None:
        line_in = self.input_source_var.get() == InputSource.LINE_IN.value
        if line_in:
            self.rtl_box.pack_forget()
            self.linein_box.pack(fill="x", pady=(8, 0))
        else:
            self.linein_box.pack_forget()
            self.rtl_box.pack(fill="x", pady=(8, 0))

    def _channels_to_text(self) -> str:
        return "\n".join(
            f"{c.channel_number},{c.frequency_hz / 1_000_000:.6f}" + (f",{c.note}" if c.note else "")
            for c in self.system.channels
        )

    def _talkgroups_to_text(self) -> str:
        return "\n".join(f"{t.talkgroup_id},{t.mode},{t.name}" for t in self.system.talkgroups)

    def _parse_channels(self) -> list[ChannelEntry]:
        entries: list[ChannelEntry] = []
        for raw in self.channels_text.get("1.0", "end").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            entries.append(
                ChannelEntry(
                    channel_number=int(parts[0]),
                    frequency_hz=int(float(parts[1]) * 1_000_000),
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
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            entries.append(Talkgroup(talkgroup_id=int(parts[0]), mode=parts[1], name=parts[2]))
        return entries

    def _save(self) -> None:
        try:
            input_source = InputSource(self.input_source_var.get())
            freq_raw = self.freq_var.get().strip()
            control_frequency_hz = int(float(freq_raw) * 1_000_000) if freq_raw else 0
            if input_source == InputSource.RTL_SDR and control_frequency_hz <= 0:
                raise ValueError("Enter a control frequency for RTL-SDR systems.")

            rigctl_raw = self.rigctl_var.get().strip()
            system = ScannerSystem(
                name=self.name_var.get().strip() or "Unnamed System",
                protocol=Protocol(self.protocol_var.get()),
                system_type=SystemType.TRUNKED if self.trunk_var.get() else SystemType.CONVENTIONAL,
                control_frequency_hz=control_frequency_hz,
                channels=self._parse_channels(),
                talkgroups=self._parse_talkgroups(),
                input_source=input_source,
                rtl_device=int(self.device_var.get() or 0),
                gain=int(self.gain_var.get() or 0),
                ppm=int(self.ppm_var.get() or 0),
                bandwidth=int(float(self.bw_var.get() or 12)),
                audio_device=self._device_id_for_label(self.audio_device_var.get()),
                input_volume=max(1, min(16, int(self.input_volume_var.get() or 1))),
                rigctl_port=int(rigctl_raw) if rigctl_raw else 0,
                use_trunking=self.trunk_var.get(),
                use_whitelist=self.whitelist_var.get(),
                modulation=self.mod_var.get(),
                notes=self.notes_var.get().strip(),
            )
        except ValueError as exc:
            messagebox.showerror("Check your settings", str(exc), parent=self)
            return

        if self.on_save:
            self.on_save(system)
        self.destroy()
