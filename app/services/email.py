"""Email service.

Sends transactional emails (verification, password reset) via SMTP. If no SMTP
host is configured (local dev), the email is logged instead of sent — so the whole
flow works locally without a mail server, and you can copy the link from the logs.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger("app.email")


def _deliver(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        # Dev mode: no SMTP configured -> log it (the link is in the body).
        log.info("EMAIL (dev, not sent)\n  to: %s\n  subject: %s\n  %s", to, subject, body)
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def send_verification(to: str, link: str) -> None:
    _deliver(
        to,
        "Verify your email — Neura",
        "Welcome to Neura!\n\n"
        f"Please verify your email address by opening this link:\n{link}\n\n"
        "If you didn't create an account, you can ignore this email.",
    )


def send_password_reset(to: str, link: str) -> None:
    _deliver(
        to,
        "Reset your password — Neura",
        "We received a request to reset your password.\n\n"
        f"Open this link to choose a new password:\n{link}\n\n"
        "This link expires shortly. If you didn't request it, ignore this email "
        "and your password will stay the same.",
    )
