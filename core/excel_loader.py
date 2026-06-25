"""Load Excel workbooks and detect phone-number tables."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from core.phone import is_valid_phone, normalize_phone

PHONE_HEADER_PATTERNS = [
    r"mobiel\s*telefoon",
    r"telefoonnummer",
    r"telefoon",
    r"mobiel",
    r"gsm",
    r"phone",
    r"mobile",
    r"cell",
]

NAME_HEADER_PATTERNS = [
    r"volledige\s*naam",
    r"naam",
    r"name",
    r"student",
    r"voornaam",
]


@dataclass
class ContactRow:
    phone_raw: str
    phone_normalized: str
    name: str
    row_index: int


@dataclass
class SheetTable:
    sheet_name: str
    headers: list[str]
    header_row: int
    rows: list[dict[str, str]]


def _cell_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _score_header(header: str, patterns: list[str]) -> int:
    header_lower = header.lower()
    best = 0
    for pattern in patterns:
        if re.search(pattern, header_lower):
            best = max(best, len(pattern))
    return best


def detect_header_row(sheet: Worksheet, max_scan: int = 20) -> Optional[int]:
    """Find the first row that looks like a table header (several non-empty cells)."""
    best_row = None
    best_count = 0
    for row_idx in range(1, min(max_scan, sheet.max_row or 1) + 1):
        values = [_cell_value(sheet.cell(row=row_idx, column=col).value)
                  for col in range(1, (sheet.max_column or 1) + 1)]
        non_empty = [v for v in values if v]
        if len(non_empty) >= 2 and len(non_empty) > best_count:
            best_count = len(non_empty)
            best_row = row_idx
    return best_row


def load_sheet_table(path: str | Path, sheet_name: str) -> SheetTable:
    wb = load_workbook(path, read_only=True, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found in workbook.")
    sheet = wb[sheet_name]
    header_row = detect_header_row(sheet)
    if header_row is None:
        wb.close()
        raise ValueError("Could not detect a table header in this sheet.")

    headers: list[str] = []
    for col in range(1, (sheet.max_column or 1) + 1):
        val = _cell_value(sheet.cell(row=header_row, column=col).value)
        if val:
            headers.append(val)

    if not headers:
        wb.close()
        raise ValueError("No column headers found in the detected header row.")

    rows: list[dict[str, str]] = []
    for row_idx in range(header_row + 1, (sheet.max_row or header_row) + 1):
        row_data: dict[str, str] = {}
        has_data = False
        for col_idx, header in enumerate(headers, start=1):
            val = _cell_value(sheet.cell(row=row_idx, column=col_idx).value)
            row_data[header] = val
            if val:
                has_data = True
        if has_data:
            rows.append(row_data)

    wb.close()
    return SheetTable(
        sheet_name=sheet_name,
        headers=headers,
        header_row=header_row,
        rows=rows,
    )


def list_sheet_names(path: str | Path) -> list[str]:
    wb = load_workbook(path, read_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names


def guess_phone_column(headers: list[str]) -> Optional[str]:
    best_header = None
    best_score = 0
    for header in headers:
        score = _score_header(header, PHONE_HEADER_PATTERNS)
        if score > best_score:
            best_score = score
            best_header = header
    return best_header


def guess_name_column(headers: list[str]) -> Optional[str]:
    best_header = None
    best_score = 0
    for header in headers:
        if _score_header(header, PHONE_HEADER_PATTERNS) > 0:
            continue
        score = _score_header(header, NAME_HEADER_PATTERNS)
        if score > best_score:
            best_score = score
            best_header = header
    return best_header


def extract_contacts(
    table: SheetTable,
    phone_column: str,
    name_column: Optional[str] = None,
    country_code: str = "+31",
) -> list[ContactRow]:
    contacts: list[ContactRow] = []
    seen_phones: set[str] = set()

    for idx, row in enumerate(table.rows, start=table.header_row + 1):
        raw = row.get(phone_column, "")
        if not raw:
            continue

        normalized = normalize_phone(raw, country_code)
        if not normalized or not is_valid_phone(normalized):
            continue

        if normalized in seen_phones:
            continue
        seen_phones.add(normalized)

        name = ""
        if name_column:
            name = row.get(name_column, "") or "Onbekende student"
        else:
            name = "Onbekende student"

        contacts.append(
            ContactRow(
                phone_raw=raw,
                phone_normalized=normalized,
                name=name,
                row_index=idx,
            )
        )

    return contacts
