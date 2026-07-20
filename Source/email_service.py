"""Send OTP emails via Gmail SMTP (free App Password)."""

from __future__ import annotations

import smtplib
import socket
from email.mime.text import MIMEText


def send_otp_email(
    to_email: str,
    otp: str,
    *,
    smtp_user: str,
    smtp_password: str,
    shop_name: str = "Phone Reseller CRM",
) -> None:
    """Send a one-time password-reset code to the shop owner's email via
    Gmail SMTP, using the App Password they saved in Settings → Email
    (a regular Gmail password won't work here — Google requires a separate
    16-character "App Password" for SMTP sign-in). Raises ValueError with a
    plain-English explanation on any failure, since this is shown directly
    to the shop owner, not just logged."""
    if not smtp_user or not smtp_password:
        raise ValueError("Gmail SMTP is not configured in Settings → Email")
    msg = MIMEText(
        f"Your password reset code is: {otp}\n\n"
        f"This code expires in 15 minutes.\n\n"
        f"If you did not request this, ignore this email.\n\n"
        f"— {shop_name}",
        "plain",
        "utf-8",
    )
    msg["Subject"] = f"{shop_name} — Password reset code"
    msg["From"] = smtp_user
    msg["To"] = to_email
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_password.strip())
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise ValueError(
            "Gmail rejected the sign-in — the App Password in Settings → Email "
            "is wrong, expired, or 2-Step Verification isn't enabled on that "
            "Gmail account. Generate a new App Password and update it in Settings."
        ) from exc
    except (smtplib.SMTPException, socket.gaierror, socket.timeout, ConnectionError, OSError) as exc:
        raise ValueError(
            f"Couldn't send the reset email (no internet, or Gmail is unreachable "
            f"right now): {exc}. Try again, or contact your vendor directly."
        ) from exc
