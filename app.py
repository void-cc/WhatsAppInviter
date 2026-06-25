"""WhatsApp Inviter - GUI application for sending bulk WhatsApp invites."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from core.excel_loader import (
    SheetTable,
    extract_contacts,
    guess_name_column,
    guess_phone_column,
    list_sheet_names,
    load_sheet_table,
)
from core.sender import SendEvent, SendStatus, WhatsAppSender
from core.settings import load_settings, save_settings

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


class WhatsAppInviterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WhatsApp Inviter - Hogeschool Leiden")
        self.geometry("900x780")
        self.minsize(800, 700)

        self.settings = load_settings()
        self.excel_path: Optional[Path] = None
        self.table: Optional[SheetTable] = None
        self.contacts = []
        self.sender = WhatsAppSender(on_event=self._on_send_event)

        self._build_ui()
        self._apply_settings_to_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # --- Step 1: Import ---
        step1 = ctk.CTkFrame(self)
        step1.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        step1.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(step1, text="Excel-bestand", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=12, pady=(12, 8), sticky="w"
        )

        self.file_label = ctk.CTkLabel(step1, text="Geen bestand gekozen", anchor="w")
        self.file_label.grid(row=1, column=0, columnspan=2, padx=12, pady=4, sticky="ew")

        ctk.CTkButton(step1, text="Kies Excel-bestand (.xlsx)", command=self._pick_excel).grid(
            row=1, column=2, padx=12, pady=4
        )

        ctk.CTkLabel(step1, text="Werkblad:").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        self.sheet_var = ctk.StringVar(value="")
        self.sheet_menu = ctk.CTkOptionMenu(
            step1, variable=self.sheet_var, values=[""], command=self._on_sheet_changed, width=300
        )
        self.sheet_menu.grid(row=2, column=1, columnspan=2, padx=12, pady=8, sticky="w")

        # --- Columns ---
        step2 = ctk.CTkFrame(self)
        step2.grid(row=1, column=0, padx=16, pady=8, sticky="ew")
        step2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(step2, text="Kolommen", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(12, 8), sticky="w"
        )

        ctk.CTkLabel(step2, text="Telefoonkolom:").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self.phone_col_var = ctk.StringVar(value="")
        self.phone_col_menu = ctk.CTkOptionMenu(
            step2, variable=self.phone_col_var, values=[""], command=self._on_columns_changed, width=400
        )
        self.phone_col_menu.grid(row=1, column=1, padx=12, pady=4, sticky="w")

        ctk.CTkLabel(step2, text="Naamkolom (optioneel):").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self.name_col_var = ctk.StringVar(value="")
        self.name_col_menu = ctk.CTkOptionMenu(
            step2, variable=self.name_col_var, values=["(geen)"], command=self._on_columns_changed, width=400
        )
        self.name_col_menu.grid(row=2, column=1, padx=12, pady=4, sticky="w")

        self.contact_count_label = ctk.CTkLabel(step2, text="0 geldige telefoonnummers gevonden")
        self.contact_count_label.grid(row=3, column=0, columnspan=2, padx=12, pady=(4, 12), sticky="w")

        # --- Step 3: Message ---
        step3 = ctk.CTkFrame(self)
        step3.grid(row=2, column=0, padx=16, pady=8, sticky="ew")
        step3.grid_columnconfigure(0, weight=1)
        step3.grid_rowconfigure(2, weight=1)

        header3 = ctk.CTkFrame(step3, fg_color="transparent")
        header3.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")
        header3.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header3, text="Bericht", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkButton(header3, text="Opslaan als standaard", width=160, command=self._save_message_default).grid(
            row=0, column=1, padx=8
        )

        options_row = ctk.CTkFrame(step3, fg_color="transparent")
        options_row.grid(row=1, column=0, padx=12, pady=4, sticky="w")

        ctk.CTkLabel(options_row, text="Landcode:").pack(side="left", padx=(0, 8))
        self.country_code_var = ctk.StringVar(value="+31")
        ctk.CTkEntry(options_row, textvariable=self.country_code_var, width=60).pack(side="left", padx=(0, 16))
        self.country_code_var.trace_add("write", lambda *_: self._refresh_contacts())

        self.message_box = ctk.CTkTextbox(step3, height=140)
        self.message_box.grid(row=2, column=0, padx=12, pady=(4, 12), sticky="ew")

        # --- Step 4: Send ---
        step4 = ctk.CTkFrame(self)
        step4.grid(row=3, column=0, padx=16, pady=8, sticky="ew")

        ctk.CTkLabel(step4, text="Versturen", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=4, padx=12, pady=(12, 8), sticky="w"
        )

        ctk.CTkLabel(
            step4,
            text="Zorg dat je bent ingelogd op WhatsApp Web in Chrome of Edge voordat je start.",
            text_color="orange",
            wraplength=800,
        ).grid(row=1, column=0, columnspan=4, padx=12, pady=4, sticky="w")

        options_frame = ctk.CTkFrame(step4, fg_color="transparent")
        options_frame.grid(row=2, column=0, columnspan=4, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(options_frame, text="Wachttijd (sec):").pack(side="left", padx=(0, 4))
        self.wait_time_var = ctk.StringVar(value="15")
        ctk.CTkEntry(options_frame, textvariable=self.wait_time_var, width=60).pack(side="left", padx=(0, 16))

        self.confirm_each_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            options_frame,
            text="Bevestig na elk bericht",
            variable=self.confirm_each_var,
        ).pack(side="left", padx=(0, 16))

        start_frame = ctk.CTkFrame(step4, fg_color="transparent")
        start_frame.grid(row=3, column=0, columnspan=4, padx=12, pady=(0, 8), sticky="w")

        ctk.CTkLabel(start_frame, text="Start vanaf:").pack(side="left", padx=(0, 4))
        self.start_var = ctk.StringVar(value="")
        self.start_combo = ctk.CTkComboBox(
            start_frame, variable=self.start_var, values=["(begin)"], width=420
        )
        self.start_combo.pack(side="left", padx=(0, 8))
        ctk.CTkButton(start_frame, text="Begin", width=70, command=self._reset_start).pack(side="left")

        btn_row = ctk.CTkFrame(step4, fg_color="transparent")
        btn_row.grid(row=4, column=0, columnspan=4, padx=12, pady=(4, 12), sticky="w")

        self.send_btn = ctk.CTkButton(btn_row, text="Start versturen", command=self._start_sending, width=140)
        self.send_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            btn_row, text="Stop", command=self._stop_sending, width=100, state="disabled", fg_color="#c0392b"
        )
        self.stop_btn.pack(side="left", padx=(0, 8))

        self.continue_btn = ctk.CTkButton(
            btn_row, text="Volgende", command=self._continue_sending, width=100, state="disabled"
        )
        self.continue_btn.pack(side="left")

        self.progress = ctk.CTkProgressBar(self)
        self.progress.grid(row=4, column=0, padx=16, pady=(0, 4), sticky="ew")
        self.progress.set(0)

        self.log_box = ctk.CTkTextbox(self, height=180, state="disabled")
        self.log_box.grid(row=5, column=0, padx=16, pady=(4, 16), sticky="nsew")

    def _apply_settings_to_ui(self) -> None:
        self.message_box.insert("1.0", self.settings.get("message", ""))
        self.country_code_var.set(self.settings.get("country_code", "+31"))
        self.wait_time_var.set(str(self.settings.get("wait_time", 15)))
        self.confirm_each_var.set(self.settings.get("confirm_each", True))

    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _pick_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Kies Excel-bestand",
            filetypes=[("Excel bestanden", "*.xlsx"), ("Alle bestanden", "*.*")],
        )
        if not path:
            return

        self.excel_path = Path(path)
        self.file_label.configure(text=str(self.excel_path))

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

        saved_phone = self.settings.get("phone_column", "")
        saved_name = self.settings.get("name_column", "")

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

        self._refresh_contacts()
        self._log(f"Geladen: {self.excel_path.name} / {sheet_name} ({len(headers)} kolommen)")

    def _on_columns_changed(self, *_args) -> None:
        self._refresh_contacts()

    def _refresh_contacts(self) -> None:
        if not self.table:
            self.contacts = []
            self.contact_count_label.configure(text="0 geldige telefoonnummers gevonden")
            return

        phone_col = self.phone_col_var.get()
        name_col = self.name_col_var.get()
        if name_col == "(geen)":
            name_col = None

        country = self.country_code_var.get().strip() or "+31"
        self.contacts = extract_contacts(
            self.table,
            phone_column=phone_col,
            name_column=name_col,
            country_code=country,
        )
        self.contact_count_label.configure(
            text=f"{len(self.contacts)} geldige telefoonnummers gevonden"
        )
        self._refresh_start_options()

    def _contact_label(self, position: int, contact) -> str:
        return f"{position} - {contact.name} ({contact.phone_normalized}) - Excel-rij {contact.row_index}"

    def _refresh_start_options(self) -> None:
        labels = ["(begin)"] + [
            self._contact_label(i + 1, c) for i, c in enumerate(self.contacts)
        ]
        self.start_combo.configure(values=labels)
        self.start_var.set("(begin)")

    def _reset_start(self) -> None:
        self.start_var.set("(begin)")

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

    def _save_message_default(self) -> None:
        self.settings["message"] = self.message_box.get("1.0", "end").strip()
        self.settings["country_code"] = self.country_code_var.get().strip()
        try:
            self.settings["wait_time"] = int(self.wait_time_var.get())
        except ValueError:
            self.settings["wait_time"] = 15
        self.settings["confirm_each"] = self.confirm_each_var.get()
        self.settings["phone_column"] = self.phone_col_var.get()
        name_col = self.name_col_var.get()
        self.settings["name_column"] = "" if name_col == "(geen)" else name_col
        if self.excel_path:
            self.settings["last_sheet"] = self.sheet_var.get()
        save_settings(self.settings)
        messagebox.showinfo("Opgeslagen", "Instellingen opgeslagen als standaard.")

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
        contacts_to_send = self.contacts[start_index:]
        if not contacts_to_send:
            messagebox.showwarning("Geen contacten", "Er zijn geen contacten vanaf het gekozen startpunt.")
            return

        first = contacts_to_send[0]
        if start_index > 0:
            start_note = (
                f"\n\nStarten vanaf #{start_index + 1}: {first.name} "
                f"({first.phone_normalized}, Excel-rij {first.row_index})."
            )
        else:
            start_note = ""

        if not messagebox.askyesno(
            "Bevestigen",
            f"Weet je zeker dat je {len(contacts_to_send)} berichten wilt versturen?{start_note}\n\n"
            "Zorg dat WhatsApp Web open en ingelogd is.",
        ):
            return

        self.sender.wait_time = wait_time
        self.sender.confirm_each = self.confirm_each_var.get()
        self.progress.set(0)
        self.send_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.continue_btn.configure(state="disabled")
        if start_index > 0:
            self._log(f"--- Start versturen (vanaf #{start_index + 1}, {first.name}) ---")
        else:
            self._log("--- Start versturen ---")

        self.sender.start(contacts_to_send, message)

    def _stop_sending(self) -> None:
        self.sender.stop()
        self._log("Stop aangevraagd...")

    def _continue_sending(self) -> None:
        self.sender.confirm_continue()
        self.continue_btn.configure(state="disabled")

    def _on_send_event(self, event: SendEvent) -> None:
        self.after(0, lambda: self._handle_send_event(event))

    def _handle_send_event(self, event: SendEvent) -> None:
        if event.total > 0:
            self.progress.set(event.index / event.total)

        if event.message:
            self._log(event.message)

        if event.status == SendStatus.WAITING_CONFIRM:
            self.continue_btn.configure(state="normal")
        elif event.status in (SendStatus.STOPPED, SendStatus.COMPLETED):
            self._finish_sending()

    def _finish_sending(self) -> None:
        self.send_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.continue_btn.configure(state="disabled")
        self._log("--- Klaar ---")


def main() -> None:
    app = WhatsAppInviterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
