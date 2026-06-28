"""Build and export a CSV report of a send run."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class SendResult:
    timestamp: str
    name: str
    phone: str
    status: str
    detail: str = ""

    @classmethod
    def now(cls, name: str, phone: str, status: str, detail: str = "") -> "SendResult":
        return cls(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            name=name,
            phone=phone,
            status=status,
            detail=detail,
        )


def export_results(results: list[SendResult], path: str | Path) -> None:
    """Write send results to a UTF-8 CSV (Excel-friendly, semicolon-separated)."""
    path = Path(path)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Tijdstip", "Naam", "Telefoonnummer", "Status", "Details"])
        for r in results:
            writer.writerow([r.timestamp, r.name, r.phone, r.status, r.detail])
