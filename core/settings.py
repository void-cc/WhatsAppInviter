"""Persist user settings to AppData."""

import json
import os
import sys
from pathlib import Path
from typing import Any


def _app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "WhatsAppInviter"
    return Path.home() / ".whatsapp_inviter"


def _settings_path() -> Path:
    return _app_data_dir() / "settings.json"


def os_prefers_reduced_motion() -> bool:
    """Return True when the OS accessibility setting requests reduced motion."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Accessibility",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AnimationEffects")
                return int(value) == 0
        except OSError:
            pass
    return False


def _bundled_default_message() -> str:
    """Load shipped default message from assets."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    path = base / "assets" / "default_message.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


DEFAULT_SETTINGS: dict[str, Any] = {
    "message": "",
    "country_code": "+31",
    "wait_time": 15,
    "confirm_each": True,
    "phone_column": "",
    "name_column": "",
    "sent_column": "",
    "last_sheet": "",
    "appearance": "Systeem",
    "skip_sent": True,
    "mark_sent": True,
    "reduced_motion": None,
}


def load_settings() -> dict[str, Any]:
    path = _settings_path()
    settings = dict(DEFAULT_SETTINGS)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                stored = json.load(f)
            settings.update(stored)
        except (json.JSONDecodeError, OSError):
            pass

    if not settings.get("message"):
        settings["message"] = _bundled_default_message()

    if settings.get("reduced_motion") is None:
        settings["reduced_motion"] = os_prefers_reduced_motion()

    return settings


def save_settings(settings: dict[str, Any]) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    to_save = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
