from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Annotated, Protocol
from urllib.parse import urlencode

from fastapi import Depends

from backend.config import Settings, get_settings

logger = logging.getLogger("backend.email")


class EmailSenderProtocol(Protocol):
    async def send_email_verification(self, recipient: str, token: str) -> None:
        ...

    async def send_password_reset(self, recipient: str, token: str) -> None:
        ...


def build_account_action_url(
    settings: Settings,
    action: str,
    token: str,
) -> str:
    fragment = urlencode({"action": action, "token": token})
    return f"{settings.frontend_public_url.rstrip('/')}/#{fragment}"


class ConsoleEmailSender:
    """Development sender that writes one-time links to local API logs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_email_verification(self, recipient: str, token: str) -> None:
        url = build_account_action_url(self._settings, "verify-email", token)
        logger.warning(
            "development_email recipient=%s purpose=verify_email url=%s",
            recipient,
            url,
        )

    async def send_password_reset(self, recipient: str, token: str) -> None:
        url = build_account_action_url(self._settings, "reset-password", token)
        logger.warning(
            "development_email recipient=%s purpose=reset_password url=%s",
            recipient,
            url,
        )


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_email_verification(self, recipient: str, token: str) -> None:
        url = build_account_action_url(self._settings, "verify-email", token)
        await self._send(
            recipient,
            "Verify your Evalflow email",
            "Verify your Evalflow account by opening this one-time link:\n\n"
            f"{url}\n\nThis link expires automatically.",
        )

    async def send_password_reset(self, recipient: str, token: str) -> None:
        url = build_account_action_url(self._settings, "reset-password", token)
        await self._send(
            recipient,
            "Reset your Evalflow password",
            "Reset your Evalflow password by opening this one-time link:\n\n"
            f"{url}\n\nIf you did not request this, ignore this email.",
        )

    async def _send(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._settings.email_from_address
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        settings = self._settings
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(
                    settings.smtp_username,
                    settings.smtp_password.get_secret_value(),
                )
            client.send_message(message)


def get_email_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailSenderProtocol:
    if settings.email_backend == "smtp":
        return SmtpEmailSender(settings)
    return ConsoleEmailSender(settings)
