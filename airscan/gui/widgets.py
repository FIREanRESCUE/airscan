from __future__ import annotations

import customtkinter as ctk

from airscan.gui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    DANGER,
    DANGER_HOVER,
    FONT_BODY,
    FONT_HEADING,
    FONT_SMALL,
    PANEL,
    PANEL_ALT,
    PROTOCOL_COLORS,
    SUCCESS,
    SUCCESS_BG,
    TEXT,
    TEXT_MUTED,
)


def section_label(parent, text: str) -> ctk.CTkLabel:
    label = ctk.CTkLabel(parent, text=text, font=FONT_HEADING, text_color=TEXT, anchor="w")
    label.pack(fill="x", pady=(0, 8))
    return label


def muted_label(parent, text: str, wrap: int | None = None) -> ctk.CTkLabel:
    kwargs = {"text": text, "font": FONT_SMALL, "text_color": TEXT_MUTED, "justify": "left", "anchor": "w"}
    if wrap:
        kwargs["wraplength"] = wrap
    label = ctk.CTkLabel(parent, **kwargs)
    label.pack(fill="x", pady=(0, 8))
    return label


def primary_button(parent, text: str, command, **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        height=40,
        font=FONT_BODY,
        fg_color=ACCENT,
        hover_color=ACCENT_HOVER,
        **kwargs,
    )


def danger_button(parent, text: str, command, **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        height=36,
        font=FONT_BODY,
        fg_color=DANGER,
        hover_color=DANGER_HOVER,
        **kwargs,
    )


def ghost_button(parent, text: str, command, **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        height=36,
        font=FONT_BODY,
        fg_color=PANEL_ALT,
        hover_color=BORDER,
        border_width=1,
        border_color=BORDER,
        **kwargs,
    )


def protocol_color(protocol_value: str, line_in: bool = False) -> str:
    if line_in:
        return PROTOCOL_COLORS["line_in"]
    value = protocol_value.lower()
    if "p25" in value:
        return PROTOCOL_COLORS["p25"]
    if "dmr" in value:
        return PROTOCOL_COLORS["dmr"]
    if "nxdn" in value:
        return PROTOCOL_COLORS["nxdn"]
    return PROTOCOL_COLORS["auto"]


class SystemCard(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        name: str,
        subtitle: str,
        badge: str,
        badge_color: str,
        selected: bool = False,
        active: bool = False,
        on_select,
        on_start,
        on_edit,
    ) -> None:
        super().__init__(
            master,
            fg_color=SUCCESS_BG if active else (PANEL_ALT if selected else PANEL),
            border_width=2 if selected else 1,
            border_color=SUCCESS if active else (ACCENT if selected else BORDER),
            corner_radius=10,
        )
        self.on_select = on_select

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))

        dot_color = SUCCESS if active else TEXT_MUTED
        ctk.CTkLabel(header, text="●", text_color=dot_color, font=("Segoe UI", 14)).pack(side="left", padx=(0, 8))
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_box, text=name, font=FONT_BODY, text_color=TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(title_box, text=subtitle, font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w").pack(fill="x")

        badge_frame = ctk.CTkFrame(header, fg_color=badge_color, corner_radius=6, height=22)
        badge_frame.pack(side="right")
        ctk.CTkLabel(badge_frame, text=badge, font=FONT_SMALL, text_color="white").pack(padx=8, pady=2)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(4, 10))

        if not active:
            ctk.CTkButton(
                actions,
                text="Start",
                width=70,
                height=28,
                font=FONT_SMALL,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                command=on_start,
            ).pack(side="left", padx=(0, 6))
        else:
            ctk.CTkLabel(actions, text="Monitoring", font=FONT_SMALL, text_color=SUCCESS).pack(side="left")

        ctk.CTkButton(
            actions,
            text="Edit",
            width=60,
            height=28,
            font=FONT_SMALL,
            fg_color=PANEL,
            hover_color=BORDER,
            command=on_edit,
        ).pack(side="left")

        for widget in (self, header, title_box):
            widget.bind("<Button-1>", lambda _e: on_select())
            for child in widget.winfo_children():
                if isinstance(child, ctk.CTkButton):
                    continue
                child.bind("<Button-1>", lambda _e: on_select())
