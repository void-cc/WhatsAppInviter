"""WhatsApp message sending via pywhatkit."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

import pywhatkit

from core.excel_loader import ContactRow
from core.message import personalize_for


class SendStatus(Enum):
    SENT = auto()
    FAILED = auto()
    SKIPPED = auto()
    WAITING_CONFIRM = auto()
    STOPPED = auto()
    COMPLETED = auto()


@dataclass
class SendEvent:
    status: SendStatus
    contact: Optional[ContactRow]
    index: int
    total: int
    message: str = ""


class WhatsAppSender:
    """Send messages in a background thread with callbacks."""

    def __init__(
        self,
        on_event: Callable[[SendEvent], None],
        wait_time: int = 15,
        confirm_each: bool = True,
    ):
        self.on_event = on_event
        self.wait_time = wait_time
        self.confirm_each = confirm_each
        self._stop_requested = False
        self._confirm_event = threading.Event()
        self._skip_current = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop_requested = True
        self._confirm_event.set()

    def confirm_continue(self) -> None:
        """User pressed continue after a sent message."""
        self._confirm_event.set()

    def skip_current(self) -> None:
        """Skip waiting and move on."""
        self._skip_current = True
        self._confirm_event.set()

    def start(self, contacts: list[ContactRow], message: str) -> None:
        if self.is_running:
            return
        self._stop_requested = False
        self._thread = threading.Thread(
            target=self._run,
            args=(contacts, message),
            daemon=True,
        )
        self._thread.start()

    def _run(self, contacts: list[ContactRow], message: str) -> None:
        total = len(contacts)
        for i, contact in enumerate(contacts):
            if self._stop_requested:
                self.on_event(
                    SendEvent(
                        status=SendStatus.STOPPED,
                        contact=contact,
                        index=i,
                        total=total,
                        message="Gestopt door gebruiker.",
                    )
                )
                break

            try:
                personalized = personalize_for(message, contact)
                pywhatkit.sendwhatmsg_instantly(
                    phone_no=contact.phone_normalized,
                    message=personalized,
                    wait_time=self.wait_time,
                    tab_close=True,
                )
                self.on_event(
                    SendEvent(
                        status=SendStatus.SENT,
                        contact=contact,
                        index=i + 1,
                        total=total,
                        message=f"Verzonden naar {contact.phone_normalized} ({contact.name})",
                    )
                )
            except Exception as exc:
                self.on_event(
                    SendEvent(
                        status=SendStatus.FAILED,
                        contact=contact,
                        index=i + 1,
                        total=total,
                        message=f"Fout bij {contact.phone_normalized}: {exc}",
                    )
                )

            if self._stop_requested:
                break

            if self.confirm_each and i < total - 1:
                self._confirm_event.clear()
                self._skip_current = False
                self.on_event(
                    SendEvent(
                        status=SendStatus.WAITING_CONFIRM,
                        contact=contact,
                        index=i + 1,
                        total=total,
                        message="Wacht op bevestiging voor volgende bericht\u2026",
                    )
                )
                self._confirm_event.wait()
                if self._stop_requested:
                    self.on_event(
                        SendEvent(
                            status=SendStatus.STOPPED,
                            contact=contact,
                            index=i + 1,
                            total=total,
                            message="Gestopt door gebruiker.",
                        )
                    )
                    break
            elif not self.confirm_each and i < total - 1:
                time.sleep(2)

        if not self._stop_requested:
            self.on_event(
                SendEvent(
                    status=SendStatus.COMPLETED,
                    contact=None,
                    index=total,
                    total=total,
                    message="Alle berichten verwerkt.",
                )
            )
        self._thread = None
