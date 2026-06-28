"""WhatsApp Inviter - GUI application for sending bulk WhatsApp invites."""

from __future__ import annotations

import math
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk

from core.excel_loader import (
    SheetTable,
    extract_contacts,
    guess_name_column,
    guess_phone_column,
    guess_sent_column,
    list_sheet_names,
    load_sheet_table,
    mark_rows_sent,
)
from core.message import FALLBACK_NAME, PLACEHOLDER_HINT, PREVIEW_SAMPLE_NAME, personalize
from core.report import SendResult, export_results
from core.sender import SendEvent, SendStatus, WhatsAppSender
from core.settings import load_settings, os_prefers_reduced_motion, save_settings

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("green")

# --- Quiet palette: tinted neutrals + one muted green accent ------------- #
# Tuples are (light, dark). Neutrals carry a faint warm tint; colour appears
# only as a single accent so the interface stays calm and legible.
BG = ("#F5F4F0", "#15191A")
SURFACE = ("#FBFAF7", "#1B201F")
INSET = ("#EDEBE5", "#242A28")
INK = ("#232724", "#E6E8E4")
INK_SOFT = ("#3F443F", "#BEC3BE")
MUTED = ("#5C615B", "#949A94")
FAINT = ("#6E736C", "#727874")
HAIRLINE = ("#E5E3DC", "#272D2A")
ACCENT = ("#2F6E4F", "#54A37C")
ACCENT_HOVER = ("#296044", "#62b389")
ACCENT_SOFT = ("#E7EFE9", "#1F2D27")
ON_ACCENT = ("#FBFAF7", "#10211A")
FOCUS_RING = ("#2F6E4F", "#62B389")
WARN = ("#7A6328", "#D4BC82")

FONT = "Segoe UI"


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _resolve(color) -> str:
    """Pick the light/dark variant of a (light, dark) colour for the active mode."""
    if isinstance(color, (tuple, list)):
        idx = 0 if ctk.get_appearance_mode() == "Light" else 1
        return color[idx]
    return color


def _lerp_color(c1: str, c2: str, t: float) -> str:
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return _rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


class _ToolTip:
    """Lightweight hover/click tooltip for a small info icon.

    Colours resolve at show-time so it always matches the active light/dark mode.
    """

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._toggle, add="+")

    def _show(self, _event=None) -> None:
        if self._tip is not None or not self.text:
            return
        bg, fg, border = _resolve(INK), _resolve(BG), _resolve(FAINT)
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        outer = tk.Frame(tip, background=border)
        outer.pack()
        tk.Label(outer, text=self.text, justify="left", wraplength=280,
                 background=bg, foreground=fg, font=(FONT, 10), padx=11, pady=8).pack(
            padx=1, pady=1)
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def _toggle(self, _event=None) -> None:
        self._hide() if self._tip is not None else self._show()


class ScrollableSelect(ctk.CTkFrame):
    """A dropdown whose option list scrolls — built for long contact lists
    (CustomTkinter's native combobox stacks every value with no scrolling).

    Reads/writes a shared ``StringVar`` so the existing range logic is unchanged.
    """

    def __init__(self, master, app, variable, values, width: int = 440,
                 max_visible: int = 11):
        super().__init__(master, fg_color="transparent")
        self._app = app
        self._var = variable
        self._values = list(values)
        self._width = width
        self._max_visible = max_visible
        self._popup = None
        self._click_bind = None
        self._key_bind = None
        self._highlight_idx = -1
        self._option_widgets: list[ctk.CTkButton] = []

        self._button = ctk.CTkButton(
            self, textvariable=variable, width=width, height=34, corner_radius=8,
            fg_color=INSET, hover_color=HAIRLINE, text_color=INK, anchor="w",
            font=app._f(12), command=self._toggle, border_width=0,
            border_color=FOCUS_RING)
        self._button.pack(fill="x")
        self._chevron = ctk.CTkLabel(self, text="\u25be", font=app._f(12),
                                     text_color=MUTED, fg_color="transparent")
        self._chevron.place(relx=1.0, rely=0.5, anchor="e", x=-10)
        self._chevron.bind("<Button-1>", lambda _e: self._toggle())

        self._button.bind("<Return>", self._on_open_key)
        self._button.bind("<Down>", self._on_open_key)
        self._button.bind("<FocusIn>", lambda _e: self._set_focus_ring(True))
        self._button.bind("<FocusOut>", lambda _e: self._set_focus_ring(False))

    def _set_focus_ring(self, active: bool) -> None:
        self._button.configure(border_width=2 if active else 0)

    def _on_open_key(self, _event=None):
        if self._popup is None:
            self._open()
        return "break"

    def configure_values(self, values) -> None:
        self._values = list(values)
        if self._popup is not None:
            self._close()

    def _toggle(self) -> None:
        self._close() if self._popup is not None else self._open()

    def _current_index(self) -> int:
        current = self._var.get()
        try:
            return self._values.index(current)
        except ValueError:
            return 0

    def _highlight_option(self, idx: int) -> None:
        if not self._option_widgets or idx < 0 or idx >= len(self._option_widgets):
            return
        self._highlight_idx = idx
        for i, btn in enumerate(self._option_widgets):
            selected = i == idx
            btn.configure(
                fg_color=ACCENT_SOFT if selected else "transparent",
                text_color=ACCENT if selected else INK_SOFT,
            )

    def _on_popup_key(self, event) -> str:
        if self._popup is None or not self._option_widgets:
            return "break"
        key = event.keysym
        if key in ("Escape",):
            self._close()
        elif key in ("Return", "space"):
            if 0 <= self._highlight_idx < len(self._values):
                self._choose(self._values[self._highlight_idx])
        elif key == "Down":
            self._highlight_option(min(self._highlight_idx + 1, len(self._values) - 1))
        elif key == "Up":
            self._highlight_option(max(self._highlight_idx - 1, 0))
        elif key == "Home":
            self._highlight_option(0)
        elif key == "End":
            self._highlight_option(len(self._values) - 1)
        return "break"

    def _open(self) -> None:
        if not self._values:
            return
        self.update_idletasks()
        x = self._button.winfo_rootx()
        y = self._button.winfo_rooty() + self._button.winfo_height() + 4
        width = self._button.winfo_width()
        if width <= 1:
            width = self._width
        rows = max(1, min(len(self._values), self._max_visible))
        height = rows * 32 + 6
        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        popup.configure(background=_resolve(FAINT))
        frame = ctk.CTkScrollableFrame(
            popup, width=width - 24, height=height, fg_color=SURFACE,
            corner_radius=0, scrollbar_button_color=FAINT,
            scrollbar_button_hover_color=MUTED)
        frame.pack(padx=1, pady=1, fill="both", expand=True)
        current = self._var.get()
        self._option_widgets = []
        start_idx = self._current_index()
        for i, value in enumerate(self._values):
            selected = value == current
            btn = ctk.CTkButton(
                frame, text=value, anchor="w", height=30, corner_radius=6,
                fg_color=ACCENT_SOFT if selected else "transparent",
                hover_color=INSET, text_color=ACCENT if selected else INK_SOFT,
                font=self._app._f(12),
                command=lambda v=value: self._choose(v))
            btn.pack(fill="x", padx=2, pady=1)
            self._option_widgets.append(btn)
        popup.wm_geometry(f"{width}x{height + 2}+{x}+{y}")
        popup.bind("<Escape>", lambda _e: self._close())
        self._popup = popup
        self._chevron.configure(text="\u25b4")
        self._click_bind = self._app.bind("<Button-1>", self._on_global_click, add="+")
        self._key_bind = self._app.bind("<KeyPress>", self._on_popup_key, add="+")
        self._highlight_option(start_idx)
        popup.focus_force()

    def _choose(self, value: str) -> None:
        self._var.set(value)
        self._close()

    def _on_global_click(self, event) -> None:
        if self._popup is None:
            return
        clicked = str(event.widget)
        if (clicked.startswith(str(self._popup))
                or clicked.startswith(str(self._button))
                or clicked == str(self._chevron)):
            return
        self._close()

    def _close(self) -> None:
        if self._click_bind is not None:
            try:
                self._app.unbind("<Button-1>", self._click_bind)
            except tk.TclError:
                pass
            self._click_bind = None
        if self._key_bind is not None:
            try:
                self._app.unbind("<KeyPress>", self._key_bind)
            except tk.TclError:
                pass
            self._key_bind = None
        self._option_widgets = []
        self._highlight_idx = -1
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
        try:
            self._chevron.configure(text="\u25be")
        except tk.TclError:
            pass


class WhatsAppInviterApp(ctk.CTk):
    def __init__(self, splash: bool = True):
        super().__init__()
        self.title("WhatsApp Inviter - Hogeschool Leiden")
        self.geometry("1080x820")
        # Stays usable when docked to ~2/5 of the screen next to WhatsApp Web.
        self.minsize(560, 600)

        self.settings = load_settings()
        self.excel_path: Optional[Path] = None
        self.table: Optional[SheetTable] = None
        self.contacts = []
        self.send_results: list[SendResult] = []
        self._sent_rows: list[int] = []
        self.sender = WhatsAppSender(on_event=self._on_send_event)

        self._steps: list[dict] = []
        self._pages: list[ctk.CTkFrame] = []
        self._current_page = 0
        self._anim_jobs: dict[str, str] = {}
        self._content: Optional[ctk.CTkFrame] = None
        self._active_page: Optional[ctk.CTkFrame] = None
        self._page_dx = 0
        self._pulsing = False
        self._splash = None
        self._cur_sf = 0.0
        self._cur_ff = 0.0
        self._reduced_motion = bool(self.settings.get("reduced_motion", os_prefers_reduced_motion()))
        self._file_tooltip: Optional[_ToolTip] = None
        self._fluid_labels: list[tuple] = []
        self._last_width = 0

        self.configure(fg_color=BG)
        self._build_ui()
        self._apply_settings_to_ui()
        self._show_page(0)
        if splash and not self._reduced_motion:
            self._build_splash()

    # ------------------------------------------------------------------ #
    #  Animation engine
    # ------------------------------------------------------------------ #
    def _cancel_anim(self, key: str) -> None:
        job = self._anim_jobs.pop(key, None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

    @property
    def reduced_motion(self) -> bool:
        return self._reduced_motion

    def _animate(self, key: str, duration_ms: int, step: Callable[[float], None],
                 done: Optional[Callable[[], None]] = None, fps: int = 60) -> None:
        """Run an eased (ease-out-quart) tween, cancelling any prior run for `key`."""
        self._cancel_anim(key)
        if self._reduced_motion:
            try:
                step(1.0)
            except tk.TclError:
                return
            if done:
                done()
            return
        start = time.perf_counter()
        interval = max(1, int(1000 / fps))

        def tick():
            t = (time.perf_counter() - start) * 1000 / duration_ms
            t = 1.0 if t >= 1 else t
            eased = 1 - (1 - t) ** 4
            try:
                step(eased)
            except tk.TclError:
                self._anim_jobs.pop(key, None)
                return
            if t < 1:
                self._anim_jobs[key] = self.after(interval, tick)
            else:
                self._anim_jobs.pop(key, None)
                if done:
                    done()

        tick()

    # ------------------------------------------------------------------ #
    #  Fonts (single family; hierarchy via weight + size + space)
    # ------------------------------------------------------------------ #
    def _f(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT, size=size, weight=weight)

    def _mono(self, size: int) -> ctk.CTkFont:
        return ctk.CTkFont(family="Consolas", size=size)

    # ------------------------------------------------------------------ #
    #  Layout scaffolding
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._hairline(self, row=1, columnspan=2)
        self._build_sidebar()
        self._build_content()
        self._build_footer()

        self.bind("<Configure>", self._on_root_configure, add="+")

    def _register_fluid_label(self, label, source, margin: int, minimum: int = 200) -> None:
        """Track a label whose wraplength should follow `source`'s width on resize."""
        self._fluid_labels.append((label, source, margin, minimum))

    def _on_root_configure(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        width = self.winfo_width()
        if width == self._last_width:
            return
        self._last_width = width
        self._refresh_fluid_labels()

        sub = getattr(self, "header_sub", None)
        if sub is not None:
            try:
                scaling = ctk.ScalingTracker.get_window_scaling(self)
            except Exception:
                scaling = 1.0
            logical_width = width / (scaling or 1.0)
            full = "Hogeschool Leiden  ·  studenten uitnodigen via WhatsApp"
            compact = "Hogeschool Leiden"
            try:
                sub.configure(text=compact if logical_width < 720 else full)
            except tk.TclError:
                pass

    def _refresh_fluid_labels(self) -> None:
        for label, source, margin, minimum in self._fluid_labels:
            try:
                avail = source.winfo_width() - margin
            except tk.TclError:
                continue
            label.configure(wraplength=max(minimum, avail))

    def _hairline(self, parent, row: int, column: int = 0, columnspan: int = 1,
                  pady=0) -> None:
        line = ctk.CTkFrame(parent, height=1, fg_color=HAIRLINE, corner_radius=0)
        line.grid(row=row, column=column, columnspan=columnspan, sticky="ew", pady=pady)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent", height=76)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_propagate(False)

        mark = ctk.CTkFrame(header, fg_color="transparent")
        mark.grid(row=0, column=0, padx=(26, 0), pady=18, sticky="w")
        ctk.CTkLabel(mark, text="WhatsApp Inviter", font=self._f(19, "bold"),
                     text_color=INK).pack(anchor="w")
        self.header_sub = ctk.CTkLabel(
            mark, text="Hogeschool Leiden  ·  studenten uitnodigen via WhatsApp",
            font=self._f(12), text_color=MUTED)
        self.header_sub.pack(anchor="w", pady=(2, 0))

        theme = ctk.CTkFrame(header, fg_color="transparent")
        theme.grid(row=0, column=1, padx=(12, 26), pady=18, sticky="e")
        self.appearance_var = ctk.StringVar(value=self.settings.get("appearance", "Systeem"))
        ctk.CTkSegmentedButton(
            theme, values=["Licht", "Donker", "Systeem"], variable=self.appearance_var,
            command=self._on_appearance_changed, font=self._f(12), height=30,
            fg_color=INSET, selected_color=("#C3E0CE", "#2F5E47"),
            selected_hover_color=("#B6D8C2", "#376B52"),
            unselected_color=INSET, unselected_hover_color=HAIRLINE,
            text_color=INK_SOFT, corner_radius=7,
        ).pack()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, fg_color="transparent", width=170)
        sidebar.grid(row=2, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(99, weight=1)

        ctk.CTkLabel(sidebar, text="Stappen", font=self._f(12, "bold"), text_color=FAINT,
                     anchor="w").grid(row=0, column=0, padx=(15, 0), pady=(15, 12), sticky="w")

        steps = [
            ("Importeren", "Excel & kolommen"),
            ("Bericht", "Tekst & voorbeeld"),
            ("Versturen", "Verzenden & log"),
        ]
        for idx, (title, sub) in enumerate(steps):
            self._steps.append(self._make_step(sidebar, idx + 1, idx, title, sub))

        rule = ctk.CTkFrame(self, width=1, fg_color=HAIRLINE, corner_radius=0)
        rule.grid(row=2, column=0, sticky="nse")

    def _make_step(self, parent, grid_row: int, idx: int, title: str, sub: str) -> dict:
        row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=8,
                           border_width=0, border_color=FOCUS_RING)
        row.grid(row=grid_row, column=0, sticky="ew", padx=(18, 14), pady=2)
        row.grid_columnconfigure(1, weight=1)

        accent = ctk.CTkFrame(row, width=3, height=34, fg_color="transparent",
                              corner_radius=2)
        accent.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(6, 14), pady=8)

        title_lbl = ctk.CTkLabel(row, text=title, font=self._f(14), text_color=MUTED,
                                 anchor="w")
        title_lbl.grid(row=0, column=1, sticky="w", pady=(8, 0))
        sub_lbl = ctk.CTkLabel(row, text=sub, font=self._f(11), text_color=FAINT, anchor="w")
        sub_lbl.grid(row=1, column=1, sticky="w", pady=(0, 8))

        nav_btn = ctk.CTkButton(
            row, text="", width=10, height=10, corner_radius=8,
            fg_color="transparent", hover_color=SURFACE, border_width=0,
            command=lambda i=idx: self._show_page(i))
        nav_btn.place(relx=0, rely=0, relwidth=1, relheight=1)
        nav_btn.lower()

        step = {"row": row, "accent": accent, "title": title_lbl, "sub": sub_lbl,
                "nav_btn": nav_btn, "idx": idx, "active": False, "focused": False}

        def activate(_event=None, page_idx=idx):
            self._show_page(page_idx)
            return "break"

        def focus_in(_event=None, s=step):
            s["focused"] = True
            if not s["active"]:
                row.configure(border_width=2)

        def focus_out(_event=None, s=step):
            s["focused"] = False
            row.configure(border_width=0)

        nav_btn.bind("<Return>", activate)
        nav_btn.bind("<space>", activate)
        nav_btn.bind("<FocusIn>", focus_in)
        nav_btn.bind("<FocusOut>", focus_out)

        for w in (row, accent, title_lbl, sub_lbl):
            w.bind("<Button-1>", lambda _e, i=idx: self._show_page(i))
            w.bind("<Enter>", lambda _e, s=step: self._hover_step(s, True))
            w.bind("<Leave>", lambda _e, s=step: self._hover_step(s, False))
            try:
                w.configure(cursor="hand2")
            except (tk.TclError, AttributeError):
                pass
        return step

    def _hover_step(self, step: dict, entering: bool) -> None:
        if step["active"]:
            return
        step["row"].configure(fg_color=SURFACE if entering else "transparent")

    _PAGE_PAD = (46, 32, 46, 18)  # left, top, right, bottom

    def _build_content(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=2, column=1, sticky="nsew")
        self._content = container

        self._page_import = self._build_page_import(container)
        self._page_message = self._build_page_message(container)
        self._page_send = self._build_page_send(container)
        self._pages = [self._page_import, self._page_message, self._page_send]

        container.bind("<Configure>", lambda _e: self._place_active())

    def _place_active(self) -> None:
        if self._active_page is None:
            return
        self._active_page.place(relx=0, rely=0, relwidth=1, relheight=1,
                                x=self._page_dx, y=0)

    def _build_footer(self) -> None:
        self._hairline(self, row=3, columnspan=2)
        footer = ctk.CTkFrame(self, fg_color="transparent", height=48)
        footer.grid(row=4, column=0, columnspan=2, sticky="ew")
        footer.grid_columnconfigure(1, weight=1)
        footer.grid_propagate(False)

        self.status_dot = ctk.CTkLabel(footer, text="\u25cf", text_color=FAINT,
                                       font=self._f(11))
        self.status_dot.grid(row=0, column=0, padx=(26, 8), pady=13)
        self.status_label = ctk.CTkLabel(footer, text="Klaar om te beginnen",
                                         font=self._f(12), text_color=MUTED, anchor="w")
        self.status_label.grid(row=0, column=1, sticky="w", pady=13, padx=(0, 26))

    # ------------------------------------------------------------------ #
    #  Launch splash
    # ------------------------------------------------------------------ #
    def _build_splash(self) -> None:
        self._splash = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._splash.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._splash.tkraise()

        center = ctk.CTkFrame(self._splash, fg_color="transparent")
        center.place(relx=0.5, rely=0.46, anchor="center")

        bg = _resolve(BG)
        mark = ctk.CTkLabel(center, text="WhatsApp Inviter", font=self._f(30, "bold"),
                            text_color=bg)
        mark.pack()
        sub = ctk.CTkLabel(center, text="Hogeschool Leiden", font=self._f(13),
                           text_color=bg)
        sub.pack(pady=(6, 0))
        bar = ctk.CTkFrame(center, height=2, width=0, fg_color=_resolve(ACCENT),
                           corner_radius=1)
        bar.pack(pady=(20, 0))

        ink, muted, accent = _resolve(INK), _resolve(MUTED), _resolve(ACCENT)

        def fade_in(e):
            mark.configure(text_color=_lerp_color(bg, ink, e))
            sub.configure(text_color=_lerp_color(bg, muted, e))
            bar.configure(width=int(160 * e))

        def fade_out(e):
            mark.configure(text_color=_lerp_color(ink, bg, e))
            sub.configure(text_color=_lerp_color(muted, bg, e))
            bar.configure(fg_color=_lerp_color(accent, bg, e))

        def dismiss():
            self._animate("splash", 320, fade_out, done=self._destroy_splash)

        def hold():
            self._anim_jobs["splash_hold"] = self.after(420, dismiss)

        self._animate("splash", 460, fade_in, done=hold)

    def _destroy_splash(self) -> None:
        if self._splash is not None:
            self._splash.destroy()
            self._splash = None

    # ------------------------------------------------------------------ #
    #  Section helpers
    # ------------------------------------------------------------------ #
    def _page_heading(self, parent, step_text: str, title: str, subtitle: str):
        block = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(block, text=step_text, font=self._f(12), text_color=ACCENT,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(block, text=title, font=self._f(23, "bold"), text_color=INK,
                     anchor="w").pack(anchor="w", pady=(3, 0))
        ctk.CTkLabel(block, text=subtitle, font=self._f(13), text_color=MUTED,
                     anchor="w").pack(anchor="w", pady=(5, 0))
        return block

    def _info_icon(self, parent, text: str):
        icon = ctk.CTkLabel(parent, text="\u24d8", font=self._f(15), text_color=MUTED,
                            cursor="hand2", width=16)
        _ToolTip(icon, text)
        return icon

    def _field_label_info(self, parent, text: str, hint: str):
        """A field label followed by an inline info icon revealing `hint` on hover."""
        block = ctk.CTkFrame(parent, fg_color="transparent")
        self._field_label(block, text).pack(side="left")
        if hint:
            self._info_icon(block, hint).pack(side="left", padx=(6, 0))
        return block

    def _section_label(self, parent, text: str):
        return ctk.CTkLabel(parent, text=text, font=self._f(13, "bold"),
                            text_color=INK_SOFT, anchor="w")

    def _field_label(self, parent, text: str):
        return ctk.CTkLabel(parent, text=text, font=self._f(13), text_color=MUTED,
                            anchor="w")

    def _menu(self, parent, var, values, command=None, width=320):
        return ctk.CTkOptionMenu(
            parent, variable=var, values=values, command=command or self._on_columns_changed,
            height=34, corner_radius=8, font=self._f(13), fg_color=INSET,
            button_color=INSET, button_hover_color=HAIRLINE, text_color=INK,
            dropdown_fg_color=SURFACE, dropdown_text_color=INK_SOFT,
            dropdown_hover_color=INSET, dynamic_resizing=False, width=width)

    def _entry(self, parent, var, width, *, validator: Optional[Callable[[], bool]] = None):
        entry = ctk.CTkEntry(parent, textvariable=var, width=width, height=34,
                             corner_radius=8, fg_color=INSET, border_width=2,
                             border_color=INSET, text_color=INK, font=self._f(13))
        if validator is not None:
            def validate(_event=None):
                ok = validator()
                entry.configure(border_color=INSET if ok else WARN)
                return ok

            entry.bind("<FocusOut>", validate)
            var.trace_add("write", lambda *_: entry.configure(border_color=INSET))
        return entry

    def _primary_btn(self, parent, text, command, width=170):
        btn = ctk.CTkButton(parent, text=text, command=command, width=width, height=40,
                            corner_radius=9, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                            text_color=ON_ACCENT, font=self._f(13, "bold"),
                            border_width=0, border_color=FOCUS_RING)
        btn.bind("<Return>", lambda _e: (command(), "break"))
        btn.bind("<FocusIn>", lambda _e: btn.configure(border_width=2))
        btn.bind("<FocusOut>", lambda _e: btn.configure(border_width=0))
        return btn

    def _ghost_btn(self, parent, text, command, width=120, accent=False):
        edge = ACCENT if accent else FAINT
        txt = ACCENT if accent else INK_SOFT
        btn = ctk.CTkButton(parent, text=text, command=command, width=width, height=40,
                            corner_radius=9, fg_color="transparent", border_width=1,
                            border_color=edge, text_color=txt, hover_color=INSET,
                            font=self._f(13))
        btn.bind("<Return>", lambda _e: (command(), "break"))
        btn.bind("<FocusIn>", lambda _e: btn.configure(border_width=2, border_color=FOCUS_RING))
        btn.bind("<FocusOut>", lambda _e: btn.configure(border_width=1, border_color=edge))
        return btn

    # ------------------------------------------------------------------ #
    #  Page 1 - Import
    # ------------------------------------------------------------------ #
    def _build_page_import(self, parent) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        page = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=(28, 22), pady=(30, 16))
        page.grid_columnconfigure(0, weight=1)

        self._page_heading(page, "Stap 1 van 3", "Importeren",
                           "Kies je Excel-export en controleer de kolommen."
                           ).grid(row=0, column=0, sticky="ew", pady=(0, 30))

        self._section_label(page, "Bronbestand").grid(row=1, column=0, sticky="w",
                                                       pady=(0, 12))
        drop = ctk.CTkFrame(page, fg_color="transparent", corner_radius=10,
                            border_width=1, border_color=HAIRLINE)
        drop.grid(row=2, column=0, sticky="ew")
        drop.grid_columnconfigure(0, weight=1)
        self.file_label = ctk.CTkLabel(drop, text="Kies een Excel-bestand om te beginnen",
                                       anchor="w", font=self._f(13), text_color=MUTED)
        self.file_label.grid(row=0, column=0, padx=18, pady=15, sticky="ew")
        ctk.CTkButton(drop, text="Bladeren", command=self._pick_excel, width=120, height=34,
                      corner_radius=8, fg_color=INSET, hover_color=HAIRLINE,
                      text_color=INK_SOFT, font=self._f(13)).grid(row=0, column=1,
                                                                  padx=9, pady=9)

        sheet_row = ctk.CTkFrame(page, fg_color="transparent")
        sheet_row.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        sheet_row.grid_columnconfigure(0, minsize=130)
        sheet_row.grid_columnconfigure(1, weight=1)
        self._field_label(sheet_row, "Werkblad").grid(row=0, column=0, sticky="w")
        self.sheet_var = ctk.StringVar(value="")
        self.sheet_menu = self._menu(sheet_row, self.sheet_var, [""],
                                     command=self._on_sheet_changed, width=320)
        self.sheet_menu.grid(row=0, column=1, sticky="ew")

        self._section_label(page, "Kolommen").grid(row=4, column=0, sticky="w",
                                                    pady=(38, 2))
        ctk.CTkLabel(page, text="Automatisch herkend - pas aan waar nodig.",
                     font=self._f(12), text_color=FAINT, anchor="w").grid(
            row=5, column=0, sticky="w", pady=(0, 14))

        cols = ctk.CTkFrame(page, fg_color="transparent")
        cols.grid(row=6, column=0, sticky="ew")
        cols.grid_columnconfigure(0, minsize=130)
        cols.grid_columnconfigure(1, weight=1)
        fields = [
            ("Telefoonkolom", "phone_col_var", [""],
             "Kolom met mobiele nummers, bijvoorbeeld Mobiel telefoonnummer."),
            ("Naamkolom", "name_col_var", ["(geen)"],
             "Voor {voornaam} en {naam} in je bericht. Kies (geen) als de kolom ontbreekt."),
            ("Verzonden-kolom", "sent_col_var", ["(geen)"],
             "Excel-vinkjes (TRUE/FALSE) om bij te houden wie al een bericht kreeg."),
        ]
        self.phone_col_var = ctk.StringVar(value="")
        self.name_col_var = ctk.StringVar(value="")
        self.sent_col_var = ctk.StringVar(value="(geen)")
        var_map = {"phone_col_var": self.phone_col_var, "name_col_var": self.name_col_var,
                   "sent_col_var": self.sent_col_var}
        for i, (label, attr, values, hint) in enumerate(fields):
            self._field_label_info(cols, label, hint).grid(
                row=i, column=0, padx=(0, 16), pady=8, sticky="w")
            menu = self._menu(cols, var_map[attr], values)
            menu.grid(row=i, column=1, pady=8, sticky="ew")
            setattr(self, attr.replace("_var", "_menu"), menu)

        self._field_label_info(
            cols, "Landcode",
            "Voor Nederlandse nummers meestal +31. 06-nummers worden automatisch omgezet."
        ).grid(row=3, column=0, padx=(0, 16), pady=8, sticky="w")
        self.country_code_var = ctk.StringVar(value="+31")

        def _validate_country_code() -> bool:
            value = self.country_code_var.get().strip()
            return bool(value) and value.startswith("+") and value[1:].isdigit()

        self._entry(cols, self.country_code_var, 88, validator=_validate_country_code).grid(
            row=3, column=1, pady=8, sticky="w")
        self.country_code_var.trace_add("write", lambda *_: self._refresh_contacts())

        result = ctk.CTkFrame(page, fg_color="transparent")
        result.grid(row=7, column=0, sticky="w", pady=(28, 0))
        self.count_number = ctk.CTkLabel(result, text="0", font=self._f(15, "bold"),
                                         text_color=INK)
        self.count_number.grid(row=0, column=0, padx=(0, 7))
        self.contact_count_label = ctk.CTkLabel(result, text="importeer een Excel-bestand",
                                                font=self._f(13), text_color=MUTED)
        self.contact_count_label.grid(row=0, column=1, sticky="w")

        nav = ctk.CTkFrame(page, fg_color="transparent")
        nav.grid(row=8, column=0, sticky="e", pady=(32, 6))
        self._primary_btn(nav, "Verder naar bericht", lambda: self._show_page(1),
                          width=190).pack(side="right")
        return outer

    # ------------------------------------------------------------------ #
    #  Page 2 - Message
    # ------------------------------------------------------------------ #
    def _build_page_message(self, parent) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        page = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=(28, 22), pady=(32, 18))
        page.grid_columnconfigure(0, weight=1)

        self._page_heading(page, "Stap 2 van 3", "Bericht",
                           "Schrijf je uitnodiging. Het voorbeeld werkt mee terwijl je typt."
                           ).grid(row=0, column=0, sticky="ew", pady=(0, 30))

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        top.grid_columnconfigure(0, weight=1)
        self._section_label(top, "Berichttekst").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(top, text=PLACEHOLDER_HINT, font=self._f(12), text_color=FAINT,
                     anchor="e").grid(row=0, column=1, sticky="e")

        self.message_box = ctk.CTkTextbox(page, height=150, corner_radius=10,
                                           font=self._f(14), fg_color=SURFACE, border_width=1,
                                           border_color=HAIRLINE, text_color=INK,
                                           scrollbar_button_color=FAINT)
        self.message_box.grid(row=2, column=0, sticky="ew")
        self.message_box.bind("<KeyRelease>", lambda _e: self._update_preview())

        preview = ctk.CTkFrame(page, fg_color="transparent")
        preview.grid(row=3, column=0, sticky="nsew", pady=(26, 0))
        preview.grid_columnconfigure(0, weight=1)
        preview.grid_rowconfigure(1, weight=1)
        self._section_label(preview, "Voorbeeld").grid(row=0, column=0, sticky="w",
                                                        pady=(0, 12))
        chat = ctk.CTkFrame(preview, fg_color=("#ECEAE3", "#171C1A"), corner_radius=10,
                            border_width=1, border_color=HAIRLINE)
        chat.grid(row=1, column=0, sticky="nsew")
        chat.grid_columnconfigure(0, weight=1)
        bubble = ctk.CTkFrame(chat, fg_color=("#DEE9E0", "#243029"), corner_radius=12)
        bubble.grid(row=0, column=0, padx=16, pady=16, sticky="e")
        self.preview_name_label = ctk.CTkLabel(bubble, text="Voorbeeld",
                                               font=self._f(11, "bold"), text_color=ACCENT,
                                               anchor="w")
        self.preview_name_label.pack(anchor="w", padx=15, pady=(11, 0))
        self.preview_label = ctk.CTkLabel(bubble, text="\u2014", anchor="w", justify="left",
                                          wraplength=540, font=self._f(13), text_color=INK)
        self.preview_label.pack(anchor="w", padx=15, pady=(2, 12))
        self._register_fluid_label(self.preview_label, chat, margin=90, minimum=180)

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", pady=(22, 4))
        self._ghost_btn(actions, "Terug", lambda: self._show_page(0), width=92).pack(
            side="left")
        self._primary_btn(actions, "Verder naar versturen", lambda: self._show_page(2),
                          width=180).pack(side="right")
        self._ghost_btn(actions, "Opslaan als standaard", self._save_message_default,
                        width=160, accent=True).pack(side="right", padx=(0, 10))
        return outer

    # ------------------------------------------------------------------ #
    #  Page 3 - Send
    # ------------------------------------------------------------------ #
    def _build_page_send(self, parent) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        page = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=(28, 22), pady=(32, 18))
        page.grid_columnconfigure(0, weight=1)

        self._page_heading(page, "Stap 3 van 3", "Versturen",
                           "Volg het verloop en start wanneer je klaar bent."
                           ).grid(row=0, column=0, sticky="ew", pady=(0, 20))

        self._build_send_progress(page).grid(row=1, column=0, sticky="ew")

        warn = ctk.CTkFrame(page, fg_color="transparent", corner_radius=9, border_width=1,
                            border_color=HAIRLINE)
        warn.grid(row=2, column=0, sticky="ew", pady=(18, 16))
        warn_label = ctk.CTkLabel(
            warn, text="Log eerst in op WhatsApp Web in Chrome of Edge voordat je start.",
            font=self._f(12), text_color=WARN, anchor="w", justify="left", wraplength=820)
        warn_label.pack(anchor="w", padx=15, pady=11)
        self._register_fluid_label(warn_label, warn, margin=34, minimum=200)

        rng = ctk.CTkFrame(page, fg_color="transparent")
        rng.grid(row=3, column=0, sticky="ew", pady=(0, 18))
        head = ctk.CTkFrame(rng, fg_color="transparent")
        head.pack(anchor="w", pady=(0, 10))
        self._section_label(head, "Bereik").pack(side="left")
        self._info_icon(
            head,
            "Kies welk deel van de lijst jij verstuurt. Zo kunnen meerdere personen "
            "dezelfde Excel verdelen zonder dubbel werk of dubbele berichten."
        ).pack(side="left", padx=(8, 0))

        grid = ctk.CTkFrame(rng, fg_color="transparent")
        grid.pack(anchor="w", fill="x")
        grid.grid_columnconfigure(0, minsize=46)
        grid.grid_columnconfigure(1, weight=1)

        self._field_label(grid, "Van").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.start_var = ctk.StringVar(value="(begin)")
        self.start_combo = ScrollableSelect(grid, self, self.start_var, ["(begin)"], width=440)
        self.start_combo.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        self._field_label(grid, "t/m").grid(row=1, column=0, sticky="w")
        self.end_var = ctk.StringVar(value="(einde)")
        self.end_combo = ScrollableSelect(grid, self, self.end_var, ["(einde)"], width=440)
        self.end_combo.grid(row=1, column=1, sticky="ew")

        self._ghost_btn(grid, "Alles", self._reset_range, width=78).grid(
            row=0, column=2, rowspan=2, padx=(12, 0))

        btns = ctk.CTkFrame(page, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="w", pady=(0, 18))
        self.send_btn = self._primary_btn(btns, "Start versturen", self._start_sending,
                                          width=160)
        self.send_btn.pack(side="left", padx=(0, 10))
        self.stop_btn = self._ghost_btn(btns, "Stop", self._stop_sending, width=92)
        self.continue_btn = self._ghost_btn(btns, "Volgende", self._continue_sending,
                                            width=110)
        self.export_btn = self._ghost_btn(btns, "Exporteer rapport", self._export_report,
                                          width=160)
        self.export_btn.configure(state="disabled")
        self.export_btn.pack(side="left")
        self._layout_send_btns()

        opts_head = ctk.CTkFrame(page, fg_color="transparent")
        opts_head.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        self._opts_open = False
        self.opts_toggle_btn = ctk.CTkButton(
            opts_head, text="Opties  \u25b8", command=self._toggle_send_opts,
            width=110, height=32, corner_radius=8, fg_color="transparent",
            border_width=1, border_color=HAIRLINE, text_color=INK_SOFT,
            hover_color=INSET, font=self._f(12), anchor="w")
        self.opts_toggle_btn.pack(anchor="w")

        self._opts_body = ctk.CTkFrame(page, fg_color="transparent")
        self._opts_body.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        self._opts_body.grid_remove()

        def _check(parent, text, var, command=None):
            return ctk.CTkCheckBox(parent, text=text, variable=var, command=command,
                                   font=self._f(13), text_color=INK_SOFT, fg_color=ACCENT,
                                   hover_color=ACCENT_HOVER, checkmark_color=ON_ACCENT,
                                   corner_radius=4, border_color=FAINT, border_width=2,
                                   checkbox_width=20, checkbox_height=20)

        def _opt_check(text, var, hint, command=None):
            row = ctk.CTkFrame(self._opts_body, fg_color="transparent")
            row.pack(anchor="w", pady=5, fill="x")
            _check(row, text, var, command).pack(side="left")
            self._info_icon(row, hint).pack(side="left", padx=(8, 0))

        self.confirm_each_var = ctk.BooleanVar(value=True)
        _opt_check("Bevestig na elk bericht", self.confirm_each_var,
                   "Pauzeer na ieder bericht zodat je kunt controleren voordat je doorgaat.")
        self.skip_sent_var = ctk.BooleanVar(value=True)
        _opt_check("Sla al verzonden over", self.skip_sent_var,
                   "Rijen die al aangevinkt zijn in Excel worden niet opnieuw aangeschreven.",
                   command=self._refresh_contacts)
        self.mark_sent_var = ctk.BooleanVar(value=True)
        _opt_check("Vink af in Excel na verzenden", self.mark_sent_var,
                   "Zet de verzonden-kolom op TRUE na afloop, zodat je de volgende keer verder kunt.")
        self.reduced_motion_var = ctk.BooleanVar(value=self._reduced_motion)
        _opt_check(
            "Verminder beweging",
            self.reduced_motion_var,
            "Schakel animaties en het startscherm uit. Volgt standaard de Windows-instelling.",
            command=self._on_reduced_motion_changed,
        )

        wait_row = ctk.CTkFrame(self._opts_body, fg_color="transparent")
        wait_row.pack(anchor="w", pady=(8, 4), fill="x")
        self._field_label(wait_row, "Wachttijd (sec)").pack(side="left")
        self.wait_time_var = ctk.StringVar(value="15")

        def _validate_wait_time() -> bool:
            try:
                value = int(self.wait_time_var.get().strip())
                return value >= 5
            except ValueError:
                return False

        self._entry(wait_row, self.wait_time_var, 66, validator=_validate_wait_time).pack(
            side="left", padx=(12, 0))
        self._info_icon(
            wait_row,
            "Pauze tussen berichten om WhatsApp niet te overbelasten (minimaal 5 seconden)."
        ).pack(side="left", padx=(8, 0))

        log_head = ctk.CTkFrame(page, fg_color="transparent")
        log_head.grid(row=7, column=0, sticky="ew", pady=(12, 12))
        self._section_label(log_head, "Log").pack(anchor="w")
        self.log_box = ctk.CTkTextbox(page, height=140, state="disabled", corner_radius=10,
                                      font=self._mono(12), fg_color=SURFACE,
                                      text_color=INK_SOFT, border_width=1,
                                      border_color=HAIRLINE, scrollbar_button_color=FAINT)
        self.log_box.grid(row=8, column=0, sticky="ew")
        self._log_placeholder = True
        self._show_log_placeholder()
        return outer

    def _toggle_send_opts(self) -> None:
        self._opts_open = not self._opts_open
        if self._opts_open:
            self._opts_body.grid()
            self.opts_toggle_btn.configure(text="Opties  \u25be")
        else:
            self._opts_body.grid_remove()
            self.opts_toggle_btn.configure(text="Opties  \u25b8")

    def _layout_send_btns(self, *, stop: bool = False, continue_: bool = False) -> None:
        """Pack send controls in order; Stop/Volgende only while sending."""
        for w in (self.send_btn, self.stop_btn, self.continue_btn, self.export_btn):
            w.pack_forget()
        self.send_btn.pack(side="left", padx=(0, 10))
        if stop:
            self.stop_btn.pack(side="left", padx=(0, 10))
        if continue_:
            self.continue_btn.pack(side="left", padx=(0, 10))
        self.export_btn.pack(side="left")

    def _build_send_progress(self, parent) -> ctk.CTkFrame:
        """A single batch meter that narrates the send instead of 4 KPI tiles."""
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid_columnconfigure(0, weight=1)

        self.progress_headline = ctk.CTkLabel(
            box, text="Nog geen contacten geladen", font=self._f(17, "bold"),
            text_color=INK_SOFT, anchor="w")
        self.progress_headline.grid(row=0, column=0, sticky="w")

        track = ctk.CTkFrame(box, height=14, corner_radius=7, fg_color=INSET)
        track.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        track.grid_propagate(False)
        self._seg_sent = ctk.CTkFrame(track, corner_radius=7, fg_color=ACCENT)
        self._seg_sent.place(relx=0, rely=0, relheight=1, relwidth=0)
        self._seg_failed = ctk.CTkFrame(track, corner_radius=7, fg_color=WARN)
        self._seg_failed.place(relx=0, rely=0, relheight=1, relwidth=0)

        legend = ctk.CTkFrame(box, fg_color="transparent")
        legend.grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.legend_sent = self._legend_item(legend, 0, ACCENT, "verzonden")
        self.legend_remaining = self._legend_item(legend, 1, FAINT, "te gaan")
        self.legend_failed = self._legend_item(legend, 2, WARN, "mislukt")
        self.legend_failed["cell"].grid_remove()
        return box

    def _legend_item(self, parent, col: int, color, caption: str) -> dict:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=col, padx=(0, 24), sticky="w")
        ctk.CTkLabel(cell, text="\u25cf", text_color=color, font=self._f(10)).pack(
            side="left", padx=(0, 7))
        val = ctk.CTkLabel(cell, text="0", font=self._f(14, "bold"), text_color=INK)
        val.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(cell, text=caption, font=self._f(12), text_color=MUTED).pack(side="left")
        return {"cell": cell, "val": val}

    def _render_progress(self, total: int, remaining: int, sent: int, failed: int) -> None:
        sending = self._pulsing
        if sending:
            headline = f"Bezig met versturen \u2014 {sent} van {total} verzonden"
            to_go = max(total - sent - failed, 0)
        elif self.send_results:
            headline = f"Klaar \u2014 {sent} verzonden"
            if failed:
                headline += f", {failed} mislukt"
            to_go = max(total - sent - failed, 0)
        elif total == 0:
            headline = "Nog geen contacten geladen"
            to_go = 0
        elif remaining == 1:
            headline = "1 student klaar om uit te nodigen"
            to_go = remaining
        else:
            headline = f"{remaining} studenten klaar om uit te nodigen"
            to_go = remaining

        self.progress_headline.configure(text=headline)
        self._set_stat(self.legend_sent["val"], sent)
        self._set_stat(self.legend_remaining["val"], to_go)
        self._set_stat(self.legend_failed["val"], failed)
        if failed:
            self.legend_failed["cell"].grid()
        else:
            self.legend_failed["cell"].grid_remove()

        sf = sent / total if total else 0.0
        ff = failed / total if total else 0.0
        self._animate_segments(sf, ff)

    def _animate_segments(self, sent_frac: float, failed_frac: float) -> None:
        s0, f0 = self._cur_sf, self._cur_ff

        def step(e):
            sf = s0 + (sent_frac - s0) * e
            ff = f0 + (failed_frac - f0) * e
            self._seg_sent.place_configure(relx=0, relwidth=sf)
            self._seg_failed.place_configure(relx=sf, relwidth=ff)

        def done():
            self._cur_sf, self._cur_ff = sent_frac, failed_frac
            self._seg_sent.place_configure(relx=0, relwidth=sent_frac)
            self._seg_failed.place_configure(relx=sent_frac, relwidth=failed_frac)

        self._animate("segs", 340, step, done)

    # ------------------------------------------------------------------ #
    #  Navigation
    # ------------------------------------------------------------------ #
    def _show_page(self, index: int) -> None:
        self._current_page = index
        for i, page in enumerate(self._pages):
            if i != index:
                page.place_forget()
        self._active_page = self._pages[index]
        self._page_dx = 24
        self._place_active()
        self._active_page.tkraise()
        self.after_idle(self._refresh_fluid_labels)

        def slide(e):
            self._page_dx = int(round(24 * (1 - e)))
            self._place_active()

        def done():
            self._page_dx = 0
            self._place_active()

        self._animate("page", 240, slide, done)

        for nav_step in self._steps:
            active = nav_step["idx"] == index
            nav_step["active"] = active
            nav_step["row"].configure(
                fg_color=SURFACE if active else "transparent",
                border_width=0 if active or not nav_step.get("focused") else 2,
            )
            nav_step["accent"].configure(fg_color=ACCENT if active else "transparent")
            nav_step["title"].configure(text_color=INK if active else MUTED)

    def _set_status(self, text: str, color=None) -> None:
        self.status_label.configure(text=text)
        if color is not None:
            self.status_dot.configure(text_color=color)

    # ------------------------------------------------------------------ #
    #  Settings / appearance
    # ------------------------------------------------------------------ #
    def _apply_settings_to_ui(self) -> None:
        self.message_box.insert("1.0", self.settings.get("message", ""))
        self.country_code_var.set(self.settings.get("country_code", "+31"))
        self.wait_time_var.set(str(self.settings.get("wait_time", 15)))
        self.confirm_each_var.set(self.settings.get("confirm_each", True))
        self.skip_sent_var.set(self.settings.get("skip_sent", True))
        self.mark_sent_var.set(self.settings.get("mark_sent", True))
        self._reduced_motion = bool(self.settings.get("reduced_motion", os_prefers_reduced_motion()))
        if hasattr(self, "reduced_motion_var"):
            self.reduced_motion_var.set(self._reduced_motion)
        self._apply_appearance(self.settings.get("appearance", "Systeem"))
        self._update_preview()
        self._update_stats()

    _APPEARANCE_MAP = {"Licht": "light", "Donker": "dark", "Systeem": "system"}

    def _apply_appearance(self, label: str) -> None:
        ctk.set_appearance_mode(self._APPEARANCE_MAP.get(label, "system"))

    def _on_appearance_changed(self, label: str) -> None:
        self._apply_appearance(label)
        self.settings["appearance"] = label

    def _on_reduced_motion_changed(self) -> None:
        self._reduced_motion = self.reduced_motion_var.get()
        self.settings["reduced_motion"] = self._reduced_motion
        if self._reduced_motion:
            self._cancel_anim("pulse")
            for key in list(self._anim_jobs):
                self._cancel_anim(key)

    def _truncate_path(self, path: Path, max_len: int = 52) -> str:
        text = str(path)
        if len(text) <= max_len:
            return text
        name = path.name
        prefix = "\u2026"
        parent_part = path.parent.name
        candidate = f"{prefix}{parent_part}/{name}"
        if len(candidate) <= max_len:
            return candidate
        if len(prefix) + len(name) <= max_len:
            return f"{prefix}{name}"
        return f"{prefix}{name[-(max_len - len(prefix)):]}"

    def _set_file_label(self, path: Path) -> None:
        display = self._truncate_path(path)
        self.file_label.configure(text=display, text_color=INK)
        if self._file_tooltip is not None:
            self._file_tooltip.text = str(path)
        else:
            self._file_tooltip = _ToolTip(self.file_label, str(path))

    def _update_preview(self) -> None:
        message = self.message_box.get("1.0", "end").strip()
        if not message:
            self.preview_label.configure(text="\u2014")
            self.preview_name_label.configure(text="Voorbeeld")
            return
        sample_name = self.contacts[0].name if self.contacts else PREVIEW_SAMPLE_NAME
        preview = personalize(message, sample_name)
        self.preview_name_label.configure(text=sample_name)
        self.preview_label.configure(text=preview)

    def _show_log_placeholder(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("1.0", "Hier verschijnt het verloop zodra je start.")
        self.log_box.configure(state="disabled")
        self._log_placeholder = True

    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        if self._log_placeholder:
            self.log_box.delete("1.0", "end")
            self._log_placeholder = False
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ #
    #  Stats
    # ------------------------------------------------------------------ #
    def _update_stats(self) -> None:
        total = len(self.contacts)
        already_sent = sum(1 for c in self.contacts if c.already_sent)
        sent_col_active = self.sent_col_var.get() != "(geen)"
        if sent_col_active and self.skip_sent_var.get():
            remaining = total - already_sent
        else:
            remaining = total
        sent = sum(1 for r in self.send_results if r.status == SendStatus.SENT.name)
        failed = sum(1 for r in self.send_results if r.status == SendStatus.FAILED.name)
        self._render_progress(total, remaining, sent, failed)

    def _set_stat(self, widget: ctk.CTkLabel, target: int) -> None:
        """Count up/down to the target value with a short eased tween."""
        try:
            start = int(widget.cget("text"))
        except (ValueError, TypeError):
            start = 0
        if start == target:
            widget.configure(text=str(target))
            return
        key = f"stat-{id(widget)}"
        self._animate(
            key, 320,
            lambda e: widget.configure(text=str(int(round(start + (target - start) * e)))),
            done=lambda: widget.configure(text=str(target)))

    def _start_pulse(self) -> None:
        self._pulsing = True
        self._pulse_phase = 0.0
        self._pulse()

    def _pulse(self) -> None:
        if not self._pulsing:
            return
        e = (math.sin(self._pulse_phase) + 1) / 2
        col = _lerp_color(_resolve(ACCENT), _resolve(BG), 0.55 * e)
        self.status_dot.configure(text_color=col)
        self._pulse_phase += 0.32
        self._anim_jobs["pulse"] = self.after(45, self._pulse)

    def _stop_pulse(self, color=None) -> None:
        self._pulsing = False
        self._cancel_anim("pulse")
        if color is not None:
            self.status_dot.configure(text_color=color)

    # ------------------------------------------------------------------ #
    #  Excel handling (logic unchanged)
    # ------------------------------------------------------------------ #
    def _pick_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Kies Excel-bestand",
            filetypes=[("Excel bestanden", "*.xlsx"), ("Alle bestanden", "*.*")],
        )
        if not path:
            return

        self.excel_path = Path(path)
        self._set_file_label(self.excel_path)

        try:
            sheets = list_sheet_names(self.excel_path)
        except Exception as exc:
            messagebox.showerror("Fout", f"Kon Excel-bestand niet openen:\n{exc}")
            return

        if not sheets:
            messagebox.showerror("Fout", "Geen werkbladen gevonden in dit bestand.")
            return

        self.sheet_menu.configure(values=sheets)
        last_sheet = self.settings.get("last_sheet", "")
        sheet = last_sheet if last_sheet in sheets else sheets[0]
        self.sheet_var.set(sheet)
        self._load_sheet(sheet)

    def _on_sheet_changed(self, sheet_name: str) -> None:
        self._load_sheet(sheet_name)

    def _load_sheet(self, sheet_name: str) -> None:
        if not self.excel_path:
            return
        try:
            self.table = load_sheet_table(self.excel_path, sheet_name)
        except Exception as exc:
            messagebox.showerror("Fout", f"Kon werkblad niet laden:\n{exc}")
            return

        headers = self.table.headers
        name_options = ["(geen)"] + headers
        self.phone_col_menu.configure(values=headers)
        self.name_col_menu.configure(values=name_options)
        self.sent_col_menu.configure(values=name_options)

        saved_phone = self.settings.get("phone_column", "")
        saved_name = self.settings.get("name_column", "")
        saved_sent = self.settings.get("sent_column", "")

        phone_guess = guess_phone_column(headers)
        phone_col = saved_phone if saved_phone in headers else (phone_guess or headers[0])
        self.phone_col_var.set(phone_col)

        name_guess = guess_name_column(headers)
        if saved_name and saved_name in headers:
            self.name_col_var.set(saved_name)
        elif name_guess:
            self.name_col_var.set(name_guess)
        else:
            self.name_col_var.set("(geen)")

        sent_guess = guess_sent_column(headers)
        if saved_sent and saved_sent in headers:
            self.sent_col_var.set(saved_sent)
        elif sent_guess:
            self.sent_col_var.set(sent_guess)
        else:
            self.sent_col_var.set("(geen)")

        self._refresh_contacts()
        self._log(f"Geladen: {self.excel_path.name} / {sheet_name} ({len(headers)} kolommen)")
        self._set_status(f"Geladen: {self.excel_path.name}", color=ACCENT)

    def _on_columns_changed(self, *_args) -> None:
        self._refresh_contacts()

    def _refresh_contacts(self) -> None:
        if not self.table:
            self.contacts = []
            self.count_number.configure(text="0")
            self.contact_count_label.configure(text="importeer een Excel-bestand")
            self._update_stats()
            return

        phone_col = self.phone_col_var.get()
        name_col = self.name_col_var.get()
        if name_col == "(geen)":
            name_col = None
        sent_col = self.sent_col_var.get()
        if sent_col == "(geen)":
            sent_col = None

        country = self.country_code_var.get().strip() or "+31"
        self.contacts = extract_contacts(
            self.table,
            phone_column=phone_col,
            name_column=name_col,
            country_code=country,
            sent_column=sent_col,
        )

        total = len(self.contacts)
        already_sent = sum(1 for c in self.contacts if c.already_sent)
        self.count_number.configure(text=str(total))
        if sent_col and self.skip_sent_var.get() and already_sent:
            remaining = total - already_sent
            self.contact_count_label.configure(
                text=f"geldige nummers  -  {already_sent} al verzonden, {remaining} te gaan"
            )
        elif sent_col and already_sent:
            self.contact_count_label.configure(
                text=f"geldige nummers  ({already_sent} al gemarkeerd als verzonden)"
            )
        else:
            self.contact_count_label.configure(text="geldige telefoonnummers gevonden")
        self._refresh_start_options()
        self._update_preview()
        self._update_stats()

    def _contact_label(self, position: int, contact) -> str:
        return f"{position} - {contact.name} ({contact.phone_normalized}) - Excel-rij {contact.row_index}"

    def _refresh_start_options(self) -> None:
        labels = [self._contact_label(i + 1, c) for i, c in enumerate(self.contacts)]
        self.start_combo.configure_values(["(begin)"] + labels)
        self.end_combo.configure_values(["(einde)"] + labels)
        self.start_var.set("(begin)")
        self.end_var.set("(einde)")

    def _reset_range(self) -> None:
        self.start_var.set("(begin)")
        self.end_var.set("(einde)")

    def _resolve_start_index(self) -> int:
        """Return the 0-based index in self.contacts to start from."""
        selected = self.start_var.get().strip()
        if not selected or selected == "(begin)":
            return 0
        try:
            position = int(selected.split(" - ", 1)[0])
        except (ValueError, IndexError):
            return 0
        return max(0, min(position - 1, len(self.contacts) - 1))

    def _resolve_end_index(self) -> int:
        """Return the 0-based index in self.contacts to stop at (inclusive)."""
        last = len(self.contacts) - 1
        selected = self.end_var.get().strip()
        if not selected or selected == "(einde)":
            return last
        try:
            position = int(selected.split(" - ", 1)[0])
        except (ValueError, IndexError):
            return last
        return max(0, min(position - 1, last))

    def _save_message_default(self) -> None:
        self.settings["message"] = self.message_box.get("1.0", "end").strip()
        self.settings["country_code"] = self.country_code_var.get().strip()
        try:
            self.settings["wait_time"] = int(self.wait_time_var.get())
        except ValueError:
            self.settings["wait_time"] = 15
        self.settings["confirm_each"] = self.confirm_each_var.get()
        self.settings["appearance"] = self.appearance_var.get()
        self.settings["skip_sent"] = self.skip_sent_var.get()
        self.settings["mark_sent"] = self.mark_sent_var.get()
        self.settings["reduced_motion"] = self.reduced_motion_var.get()
        self.settings["phone_column"] = self.phone_col_var.get()
        name_col = self.name_col_var.get()
        self.settings["name_column"] = "" if name_col == "(geen)" else name_col
        sent_col = self.sent_col_var.get()
        self.settings["sent_column"] = "" if sent_col == "(geen)" else sent_col
        if self.excel_path:
            self.settings["last_sheet"] = self.sheet_var.get()
        save_settings(self.settings)
        messagebox.showinfo("Opgeslagen", "Instellingen opgeslagen als standaard.")

    # ------------------------------------------------------------------ #
    #  Sending (logic unchanged)
    # ------------------------------------------------------------------ #
    def _start_sending(self) -> None:
        if not self.contacts:
            messagebox.showwarning("Geen contacten", "Importeer eerst een Excel-bestand met telefoonnummers.")
            return

        message = self.message_box.get("1.0", "end").strip()
        if not message:
            messagebox.showwarning("Geen bericht", "Voer eerst een bericht in.")
            return

        try:
            wait_time = int(self.wait_time_var.get())
            if wait_time < 5:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Ongeldige wachttijd", "Wachttijd moet minimaal 5 seconden zijn.")
            return

        start_index = self._resolve_start_index()
        end_index = self._resolve_end_index()
        if end_index < start_index:
            messagebox.showwarning(
                "Ongeldig bereik",
                "De 't/m'-keuze ligt vóór de 'Van'-keuze. Pas het bereik aan.",
            )
            return
        contacts_to_send = self.contacts[start_index:end_index + 1]
        full_range = start_index == 0 and end_index == len(self.contacts) - 1

        sent_col_active = self.sent_col_var.get() != "(geen)"
        skipped_already = 0
        if sent_col_active and self.skip_sent_var.get():
            before = len(contacts_to_send)
            contacts_to_send = [c for c in contacts_to_send if not c.already_sent]
            skipped_already = before - len(contacts_to_send)

        if not contacts_to_send:
            messagebox.showwarning(
                "Geen contacten",
                "Er zijn geen contacten om te versturen in het gekozen bereik "
                "(mogelijk zijn ze al gemarkeerd als verzonden).",
            )
            return

        first = contacts_to_send[0]
        if not full_range:
            start_note = (
                f"\n\nBereik #{start_index + 1} t/m #{end_index + 1}, "
                f"te beginnen bij {first.name} ({first.phone_normalized})."
            )
        else:
            start_note = ""
        if skipped_already:
            start_note += f"\n{skipped_already} contact(en) overgeslagen (al verzonden)."

        if not messagebox.askyesno(
            "Bevestigen",
            f"Weet je zeker dat je {len(contacts_to_send)} berichten wilt versturen?{start_note}\n\n"
            "Zorg dat WhatsApp Web open en ingelogd is.",
        ):
            return

        self.sender.wait_time = wait_time
        self.sender.confirm_each = self.confirm_each_var.get()
        self.send_results = []
        self._sent_rows = []
        self.send_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self._layout_send_btns(stop=True)
        self._update_stats()
        self._set_status("Actief", color=ACCENT)
        self._start_pulse()
        if not full_range:
            self._log(f"--- Start versturen (bereik #{start_index + 1} t/m "
                      f"#{end_index + 1}) ---")
        else:
            self._log("--- Start versturen ---")

        self.sender.start(contacts_to_send, message)

    def _stop_sending(self) -> None:
        self.sender.stop()
        self._log("Stop aangevraagd\u2026")
        self._stop_pulse()
        self._set_status("Stoppen\u2026", color=WARN)

    def _continue_sending(self) -> None:
        self.sender.confirm_continue()
        self._layout_send_btns(stop=True)

    def _on_send_event(self, event: SendEvent) -> None:
        self.after(0, lambda: self._handle_send_event(event))

    def _handle_send_event(self, event: SendEvent) -> None:
        if event.message:
            self._log(event.message)

        if event.contact is not None and event.status in (
            SendStatus.SENT,
            SendStatus.FAILED,
            SendStatus.SKIPPED,
        ):
            self.send_results.append(
                SendResult.now(
                    name=event.contact.name,
                    phone=event.contact.phone_normalized,
                    status=event.status.name,
                    detail=event.message,
                )
            )
            if event.status == SendStatus.SENT and event.contact.row_index:
                self._sent_rows.append(event.contact.row_index)
            self._update_stats()

        if event.status == SendStatus.WAITING_CONFIRM:
            self._layout_send_btns(stop=True, continue_=True)
            self._set_status("Wacht op jou", color=WARN)
        elif event.status in (SendStatus.STOPPED, SendStatus.COMPLETED):
            self._finish_sending()

    def _export_report(self) -> None:
        if not self.send_results:
            messagebox.showinfo("Geen gegevens", "Er zijn nog geen verzendresultaten om te exporteren.")
            return
        path = filedialog.asksaveasfilename(
            title="Rapport opslaan",
            defaultextension=".csv",
            initialfile="whatsapp_rapport.csv",
            filetypes=[("CSV-bestand", "*.csv"), ("Alle bestanden", "*.*")],
        )
        if not path:
            return
        try:
            export_results(self.send_results, path)
        except Exception as exc:
            messagebox.showerror("Fout", f"Kon rapport niet opslaan:\n{exc}")
            return
        sent = sum(1 for r in self.send_results if r.status == SendStatus.SENT.name)
        failed = sum(1 for r in self.send_results if r.status == SendStatus.FAILED.name)
        messagebox.showinfo(
            "Rapport opgeslagen",
            f"Rapport opgeslagen:\n{path}\n\nVerzonden: {sent}  |  Mislukt: {failed}",
        )

    def _finish_sending(self) -> None:
        self._stop_pulse()
        self.send_btn.configure(state="normal")
        self._layout_send_btns()
        if self.send_results:
            self.export_btn.configure(state="normal")
            sent = sum(1 for r in self.send_results if r.status == SendStatus.SENT.name)
            failed = sum(1 for r in self.send_results if r.status == SendStatus.FAILED.name)
            self._log(f"--- Klaar --- (verzonden: {sent}, mislukt: {failed})")
            self._set_status("Afgerond", color=ACCENT)
        else:
            self._log("--- Klaar ---")
            self._set_status("Klaar", color=ACCENT)
        self._update_stats()
        self._write_back_sent()

    def _write_back_sent(self) -> None:
        sent_col = self.sent_col_var.get()
        if (
            not self.mark_sent_var.get()
            or sent_col == "(geen)"
            or not self._sent_rows
            or not self.excel_path
            or not self.table
        ):
            return

        rows = self._sent_rows
        self._sent_rows = []
        try:
            updated = mark_rows_sent(
                self.excel_path,
                sheet_name=self.table.sheet_name,
                column_header=sent_col,
                header_row=self.table.header_row,
                row_numbers=rows,
            )
            self._log(f"{updated} rij(en) afgevinkt in Excel-kolom '{sent_col}'.")
            self._load_sheet(self.sheet_var.get())
        except PermissionError:
            messagebox.showwarning(
                "Excel-bestand is geopend",
                "Kon de Excel niet bijwerken omdat het bestand open is.\n"
                "Sluit het bestand in Excel en stuur eventueel opnieuw, "
                "of werk de kolom handmatig bij.",
            )
        except Exception as exc:
            messagebox.showerror("Fout", f"Kon Excel niet bijwerken:\n{exc}")


def main() -> None:
    app = WhatsAppInviterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
