"""
email.py — thin wrapper around smtplib for transactional emails.

If SMTP_HOST is not configured the email body is printed to stdout so
developers can test the flow locally without a real mail server.
"""
import smtplib
import ssl
import logging
import html as html_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders as email_encoders

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

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], to, msg.as_string())
    except Exception:
        # Log the error for ops visibility but never surface SMTP internals
        # (credentials, host) to the caller.
        logger.exception("SMTP send failed to %s", to)


def send_document_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str,
    pdf_bytes: bytes,
    filename: str,
) -> None:
    """Send an email with the PDF document attached."""
    if not settings.SMTP_HOST:
        logger.info("[EMAIL — no SMTP configured] To: %s | Subject: %s\n%s", to, subject, body_text)
        return

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to

    # Email body (text + HTML alternative)
    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(body_text, "plain"))
    body_part.attach(MIMEText(body_html, "html"))
    msg.attach(body_part)

    # PDF attachment
    attachment = MIMEBase("application", "pdf")
    attachment.set_payload(pdf_bytes)
    email_encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], to, msg.as_string())
    except Exception:
        logger.exception("SMTP send failed to %s", to)


def send_password_reset_email(to: str, full_name: str, reset_link: str) -> None:
    subject = "Reset your BillFlow password"

    # Escape user-supplied values before embedding in HTML to prevent injection.
    safe_name = html_lib.escape(full_name)
    safe_link = html_lib.escape(reset_link)

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
      <p>Hi <strong>{safe_name}</strong>,</p>
      <p>We received a request to reset your password. Click the button below —
         this link is valid for <strong>1 hour</strong>.</p>
      <a href="{safe_link}"
         style="display:inline-block;margin:24px 0;padding:12px 24px;
                background:#2563eb;color:#fff;border-radius:8px;
                text-decoration:none;font-weight:600">
        Reset password
      </a>
      <p style="color:#64748b;font-size:13px">
        If the button doesn't work, copy and paste this link into your browser:<br>
        <a href="{safe_link}" style="color:#2563eb">{safe_link}</a>
      </p>
      <p style="color:#64748b;font-size:13px">
        If you didn't request a password reset, you can safely ignore this email.
      </p>
    </div>
    """

    _send(to, subject, html, text)
