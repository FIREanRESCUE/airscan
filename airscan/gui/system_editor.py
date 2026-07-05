from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox

from airscan.models import ChannelEntry, InputSource, Protocol, ScannerSystem, SystemType, Talkgroup


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

INPUT_SOURCE_LABELS = {
    InputSource.RTL_SDR: "RTL-SDR dongle",
    InputSource.LINE_IN: "Radio aux / line-in (Baofeng, scanner, etc.)",
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
        self.system = system or ScannerSystem(name="New System", protocol=Protocol.AUTO)

        self.title("System Editor")
        self.geometry("760x760")
        self.grab_set()

        form = ctk.CTkScrollableFrame(self)
        form.pack(fill="both", expand=True, padx=16, pady=16)

        self.name_var = ctk.StringVar(value=self.system.name)
        self.protocol_var = ctk.StringVar(value=self.system.protocol.value)
        self.input_source_var = ctk.StringVar(value=self.system.input_source.value)
        self.freq_var = ctk.StringVar(value=f"{self.system.control_frequency_hz / 1_000_000:.6f}")
        self.device_var = ctk.StringVar(value=str(self.system.rtl_device))
        self.gain_var = ctk.StringVar(value=str(self.system.gain))
        self.ppm_var = ctk.StringVar(value=str(self.system.ppm))
        self.bw_var = ctk.StringVar(value=str(self.system.bandwidth))
        self.audio_device_var = ctk.StringVar(value=self._label_for_device(self.system.audio_device))
        self.input_volume_var = ctk.StringVar(value=str(self.system.input_volume))
        self.rigctl_var = ctk.StringVar(value=str(self.system.rigctl_port or ""))
        self.mod_var = ctk.StringVar(value=self.system.modulation)
        self.trunk_var = ctk.BooleanVar(value=self.system.use_trunking)
        self.whitelist_var = ctk.BooleanVar(value=self.system.use_whitelist)
        self.notes_var = ctk.StringVar(value=self.system.notes)

        self._field(form, "System name", self.name_var)
        self._combo(form, "Protocol", self.protocol_var, [p.value for p in Protocol], PROTOCOL_LABELS)
        self._combo(
            form,
            "Audio input source",
            self.input_source_var,
            [s.value for s in InputSource],
            INPUT_SOURCE_LABELS,
            on_change=self._toggle_input_sections,
        )

        self.rtl_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.rtl_frame.pack(fill="x")
        self._field(self.rtl_frame, "Control frequency (MHz)", self.freq_var)
        self._field(self.rtl_frame, "RTL-SDR device index", self.device_var)
        self._field(self.rtl_frame, "Gain (0=auto, 1-49 manual dB)", self.gain_var)
        self._field(self.rtl_frame, "PPM correction", self.ppm_var)
        self._field(self.rtl_frame, "Bandwidth (MHz)", self.bw_var)

        self.linein_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.linein_frame.pack(fill="x")
        ctk.CTkLabel(
            self.linein_frame,
            text=(
                "Connect the radio speaker/earphone jack to your PC line-in or mic input.\n"
                "Tune the radio manually to the digital channel. Trunk follow only works if rigctl is configured."
            ),
            justify="left",
            text_color="#aaaaaa",
            wraplength=680,
        ).pack(anchor="w", pady=(8, 8))
        self._combo(
            self.linein_frame,
            "Input device",
            self.audio_device_var,
            [label for _, label in self.audio_devices],
        )
        self._field(self.linein_frame, "Input boost (1-16, try 2-4 for quiet aux)", self.input_volume_var)
        self._field(self.linein_frame, "Rigctl port (optional, e.g. 4532 for SDR++)", self.rigctl_var)

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

        self._toggle_input_sections()

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
            self.rtl_frame.pack_forget()
            self.linein_frame.pack(fill="x")
            if self.protocol_var.get() == Protocol.P25_TRUNK.value:
                self.protocol_var.set(Protocol.AUTO.value)
        else:
            self.linein_frame.pack_forget()
            self.rtl_frame.pack(fill="x")

    def _field(self, parent, label: str, variable) -> None:
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", pady=(8, 2))
        ctk.CTkEntry(parent, textvariable=variable).pack(fill="x")

    def _combo(
        self,
        parent,
        label: str,
        variable,
        values: list[str],
        labels: dict | None = None,
        on_change=None,
    ) -> None:
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", pady=(8, 2))
        display = [labels.get(v, v) if labels else v for v in values]
        combo = ctk.CTkComboBox(parent, values=display)

        def apply_choice(choice: str) -> None:
            variable.set(values[display.index(choice)])
            if on_change:
                on_change(choice)

        current = labels.get(variable.get(), variable.get()) if labels else variable.get()
        combo.set(current)
        combo.configure(command=apply_choice)
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
            input_source = InputSource(self.input_source_var.get())
            rigctl_raw = self.rigctl_var.get().strip()
            rigctl_port = int(rigctl_raw) if rigctl_raw else 0
            control_frequency_hz = 0
            if input_source == InputSource.RTL_SDR:
                control_frequency_hz = int(float(self.freq_var.get()) * 1_000_000)

            system = ScannerSystem(
                name=self.name_var.get().strip() or "Unnamed System",
                protocol=Protocol(self.protocol_var.get()),
                system_type=SystemType.TRUNKED if self.trunk_var.get() else SystemType.CONVENTIONAL,
                control_frequency_hz=control_frequency_hz,
                channels=self._parse_channels(),
                talkgroups=self._parse_talkgroups(),
                input_source=input_source,
                rtl_device=int(self.device_var.get()),
                gain=int(self.gain_var.get()),
                ppm=int(self.ppm_var.get()),
                bandwidth=int(float(self.bw_var.get())),
                audio_device=self._device_id_for_label(self.audio_device_var.get()),
                input_volume=max(1, min(16, int(self.input_volume_var.get()))),
                rigctl_port=rigctl_port,
                use_trunking=self.trunk_var.get(),
                use_whitelist=self.whitelist_var.get(),
                modulation=self.mod_var.get(),
                notes=self.notes_var.get().strip(),
            )
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return

        if input_source == InputSource.LINE_IN and system.use_trunking and system.rigctl_port <= 0:
            if not messagebox.askyesno(
                "Trunking note",
                "Line-in trunking usually needs rigctl so the decoder can retune your radio/SDR.\n"
                "Without rigctl, keep the radio tuned manually and use conventional mode instead.\n\n"
                "Save anyway?",
                parent=self,
            ):
                return

        if self.on_save:
            self.on_save(system)
        self.destroy()
