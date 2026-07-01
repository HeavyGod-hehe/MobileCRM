"""Send OTP emails via Gmail SMTP (free App Password)."""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText


def send_otp_email(
    to_email: str,
    otp: str,
    *,
    smtp_user: str,
    smtp_password: str,
    shop_name: str = "Phone Reseller CRM",
) -> None:
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
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_password.strip())
        server.send_message(msg)
