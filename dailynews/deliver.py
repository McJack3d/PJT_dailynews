"""Email the issue to a Send to Kindle address over SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path

from .config import Secrets

log = logging.getLogger(__name__)

MAX_BYTES = 45 * 1024 * 1024  # Send to Kindle rejects emails over ~50 MB.


def build_message(epub_path: Path, secrets: Secrets, subject: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = secrets.sender_email
    msg["To"] = secrets.kindle_email
    if secrets.bcc:
        msg["Bcc"] = secrets.bcc
    msg["Subject"] = subject
    msg.set_content("Your daily issue is attached. Sent automatically by dailynews.\n")
    msg.add_attachment(
        epub_path.read_bytes(),
        maintype="application",
        subtype="epub+zip",
        filename=epub_path.name,
    )
    return msg


def send(epub_path: str | Path, secrets: Secrets, subject: str, retries: int = 3) -> None:
    epub_path = Path(epub_path)
    size = epub_path.stat().st_size
    if size > MAX_BYTES:
        raise RuntimeError(f"{epub_path.name} is {size / 1e6:.1f} MB, over the Kindle limit")
    msg = build_message(epub_path, secrets, subject)
    context = ssl.create_default_context()
    for attempt in range(1, retries + 1):
        try:
            if secrets.smtp_port == 465:
                server = smtplib.SMTP_SSL(secrets.smtp_host, 465, context=context, timeout=60)
            else:
                server = smtplib.SMTP(secrets.smtp_host, secrets.smtp_port, timeout=60)
                server.starttls(context=context)
            with server:
                server.login(secrets.smtp_user, secrets.smtp_password)
                server.send_message(msg)
            log.info("Sent %s (%.0f KB) to %s", epub_path.name, size / 1024, _mask(msg["To"]))
            return
        except smtplib.SMTPAuthenticationError:
            raise  # retrying won't fix bad credentials
        except (smtplib.SMTPException, OSError) as e:
            if attempt == retries:
                raise
            wait = 5 * 2 ** (attempt - 1)
            log.warning("SMTP attempt %d failed (%s); retrying in %ds", attempt, e, wait)
            time.sleep(wait)


def _mask(address: str) -> str:
    """Keep Kindle addresses out of public Actions logs."""
    user, _, domain = address.partition("@")
    return f"{user[:2]}***@{domain}"
