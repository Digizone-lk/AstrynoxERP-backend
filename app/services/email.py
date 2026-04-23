"""
email.py — thin wrapper around smtplib for transactional emails.

If SMTP_HOST is not configured the email body is printed to stdout so
developers can test the flow locally without a real mail server.
"""
import smtplib
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, html: str, text: str) -> None:
    if not settings.SMTP_HOST:
        logger.info("[EMAIL — no SMTP configured] To: %s | Subject: %s\n%s", to, subject, text)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(msg["From"], to, msg.as_string())


def send_password_reset_email(to: str, full_name: str, reset_link: str) -> None:
    subject = "Reset your BillFlow password"

    text = (
        f"Hi {full_name},\n\n"
        "We received a request to reset your BillFlow password.\n\n"
        f"Click the link below to set a new password (valid for 1 hour):\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email.\n\n"
        "— The BillFlow Team"
    )

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px;color:#1e293b">
      <h2 style="color:#2563eb;margin-bottom:4px">BillFlow</h2>
      <p style="color:#64748b;margin-top:0">Password reset request</p>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
      <p>Hi <strong>{full_name}</strong>,</p>
      <p>We received a request to reset your password. Click the button below —
         this link is valid for <strong>1 hour</strong>.</p>
      <a href="{reset_link}"
         style="display:inline-block;margin:24px 0;padding:12px 24px;
                background:#2563eb;color:#fff;border-radius:8px;
                text-decoration:none;font-weight:600">
        Reset password
      </a>
      <p style="color:#64748b;font-size:13px">
        If the button doesn't work, copy and paste this link into your browser:<br>
        <a href="{reset_link}" style="color:#2563eb">{reset_link}</a>
      </p>
      <p style="color:#64748b;font-size:13px">
        If you didn't request a password reset, you can safely ignore this email.
      </p>
    </div>
    """

    _send(to, subject, html, text)
