"""Personalize message templates with contact details."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.excel_loader import ContactRow

PLACEHOLDER_HINT = "Gebruik {voornaam} of {naam} om het bericht te personaliseren."

FALLBACK_NAME = "student"
PREVIEW_SAMPLE_NAME = "Jan Jansen"


def first_name(full_name: str) -> str:
    """Return the first word of a name, cleaned up."""
    if not full_name:
        return ""
    cleaned = full_name.strip()
    if not cleaned:
        return ""
    # Handle "Achternaam, Voornaam" style by taking the part after the comma.
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[1].strip() or cleaned
    return cleaned.split()[0] if cleaned.split() else ""


def personalize(message: str, name: str) -> str:
    """Replace {naam}/{voornaam} placeholders (case-insensitive) in a message."""
    if not message:
        return message

    full = name.strip() if name else ""
    fname = first_name(full)

    def _name_repl(_match: re.Match) -> str:
        return full or FALLBACK_NAME

    def _first_repl(_match: re.Match) -> str:
        return fname or full or FALLBACK_NAME

    result = re.sub(r"\{\s*voornaam\s*\}", _first_repl, message, flags=re.IGNORECASE)
    result = re.sub(r"\{\s*naam\s*\}", _name_repl, result, flags=re.IGNORECASE)
    return result


def personalize_for(message: str, contact: "ContactRow") -> str:
    return personalize(message, getattr(contact, "name", "") or "")
