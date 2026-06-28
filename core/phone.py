"""Phone number normalization utilities."""

import re
from typing import Optional


def normalize_phone(raw: str, country_code: str = "+31") -> Optional[str]:
    """Normalize a phone number to international format.

    - Strips spaces, dashes, and parentheses
    - Leading 0 -> country code (e.g. 0612345678 -> +31612345678)
    - Leading 00 -> international prefix (e.g. 0031... -> +31...)
    - No leading + -> prepend country code
    """
    if not raw or not str(raw).strip():
        return None

    clean = str(raw).strip()
    clean = re.sub(r"[\s\-\(\)]", "", clean)

    if not clean:
        return None

    # Remove any non-digit except leading +
    if clean.startswith("+"):
        digits = "+" + re.sub(r"\D", "", clean[1:])
    else:
        digits = re.sub(r"\D", "", clean)

    if not digits or digits == "+":
        return None

    cc = country_code if country_code.startswith("+") else f"+{country_code}"

    if digits.startswith("+"):
        return digits

    if digits.startswith("00"):
        return "+" + digits[2:]

    if digits.startswith("0"):
        return cc + digits[1:]

    return cc + digits


def is_valid_phone(normalized: str) -> bool:
    """Basic validation: must start with + and have at least 10 digits."""
    if not normalized or not normalized.startswith("+"):
        return False
    digit_count = sum(c.isdigit() for c in normalized)
    return digit_count >= 10
