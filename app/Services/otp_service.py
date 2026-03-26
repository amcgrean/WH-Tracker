"""
otp_service.py
--------------
Generates, stores, verifies, and emails one-time passcodes for passwordless login.

Email delivery uses SMTP (Office 365 / any TLS provider).
Set OTP_SMTP_* vars to override defaults.  Falls back to console-printing the
code in development if SMTP is not configured (AUTH_OTP_CONSOLE=true).

Phase 2 note: add a `send_otp_sms(phone, code)` function here using Twilio.
"""

import logging
import os
import random
import smtplib
import string
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.extensions import db
from app.Models.models import OTPCode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
OTP_MAX_REQUESTS = 3          # max codes per email per rate-limit window
OTP_RATE_WINDOW_MINUTES = 15  # rate-limit window


def _cfg(key, default=""):
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Code generation & storage
# ---------------------------------------------------------------------------

def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def generate_otp(email: str) -> tuple[str | None, str | None]:
    """
    Create a new OTP for *email*.

    Returns (code, error_message).  On rate-limit returns (None, error_str).
    """
    email = email.strip().lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Rate-limit check: how many non-expired, unused codes in the window?
    window_start = now - timedelta(minutes=OTP_RATE_WINDOW_MINUTES)
    recent = OTPCode.query.filter(
        OTPCode.email == email,
        OTPCode.created_at >= window_start,
        OTPCode.used == False,  # noqa: E712
    ).count()

    if recent >= OTP_MAX_REQUESTS:
        return None, f"Too many code requests. Please wait {OTP_RATE_WINDOW_MINUTES} minutes."

    # Invalidate any previous unused codes for this email
    OTPCode.query.filter(
        OTPCode.email == email,
        OTPCode.used == False,  # noqa: E712
    ).update({"used": True})

    code = _generate_code()
    otp = OTPCode(
        email=email,
        code=code,
        created_at=now,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        used=False,
    )
    db.session.add(otp)
    db.session.commit()
    return code, None


def verify_otp(email: str, code: str) -> tuple[bool, str]:
    """
    Verify *code* for *email*.

    Returns (success: bool, message: str).
    """
    email = email.strip().lower()
    code = (code or "").strip()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    otp = (
        OTPCode.query
        .filter(
            OTPCode.email == email,
            OTPCode.used == False,  # noqa: E712
            OTPCode.expires_at > now,
        )
        .order_by(OTPCode.created_at.desc())
        .first()
    )

    if not otp:
        return False, "Code not found or expired. Please request a new code."

    if otp.code != code:
        return False, "Incorrect code. Please try again."

    otp.used = True
    db.session.commit()
    return True, "OK"


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def _build_html(code: str, app_name: str) -> str:
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto;">
        <h2 style="color: #004526;">{app_name}</h2>
        <p>Use the code below to sign in. It expires in {OTP_EXPIRY_MINUTES} minutes.</p>
        <div style="font-size: 2.5rem; font-weight: bold; letter-spacing: 0.35em;
                    background: #f4f4f4; padding: 20px; text-align: center;
                    border-radius: 8px; margin: 24px 0; color: #004526;">
            {code}
        </div>
        <p style="color: #666; font-size: 0.85rem;">
            If you didn't request this code, you can safely ignore this email.
        </p>
    </div>
    """


def _send_via_resend(to_email: str, subject: str, html: str) -> tuple[bool, str]:
    """Send using the Resend HTTP API (RESEND_API_KEY must be set)."""
    try:
        import resend as resend_sdk
    except ImportError:
        return False, "resend package not installed (pip install resend)."

    resend_sdk.api_key = _cfg("RESEND_API_KEY")
    from_addr = _cfg("OTP_EMAIL_FROM", _cfg("EMAIL_ADDRESS", "noreply@beisserlumber.com"))
    app_name = _cfg("OTP_APP_NAME", "Beisser Ops")

    try:
        resend_sdk.Emails.send({
            "from": f"{app_name} <{from_addr}>",
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        return True, "sent-resend"
    except Exception as exc:
        logger.error("Resend send failed: %s", exc)
        return False, f"Resend error: {exc}"


def _send_via_smtp(to_email: str, subject: str, html: str) -> tuple[bool, str]:
    """Send using SMTP (Office 365 default, or any STARTTLS provider)."""
    # Resend SMTP relay uses username="resend", not the from address.
    # Generic SMTP uses OTP_SMTP_USER (defaults to from address for O365/Gmail).
    from_addr  = _cfg("OTP_EMAIL_FROM", _cfg("EMAIL_ADDRESS"))
    smtp_user  = _cfg("OTP_SMTP_USER", from_addr)   # override to "resend" for Resend SMTP relay
    smtp_pass  = _cfg("OTP_EMAIL_PASSWORD", _cfg("EMAIL_PASSWORD"))
    smtp_server = _cfg("OTP_SMTP_SERVER", "smtp.office365.com")
    smtp_port  = int(_cfg("OTP_SMTP_PORT", "587"))

    if not smtp_user or not smtp_pass:
        logger.warning(
            "SMTP credentials not configured. "
            "Set RESEND_API_KEY for Resend or OTP_EMAIL_FROM/OTP_EMAIL_PASSWORD for SMTP. "
            "Use AUTH_OTP_CONSOLE=true for dev."
        )
        return False, "Email not configured."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_email], msg.as_string())
        return True, "sent-smtp"
    except smtplib.SMTPAuthenticationError:
        logger.error("OTP SMTP auth failed for user %s", smtp_user)
        return False, "SMTP authentication failed."
    except Exception as exc:
        logger.error("OTP SMTP send failed: %s", exc)
        return False, f"Could not send email: {exc}"


def send_otp_email(email: str, code: str) -> tuple[bool, str]:
    """
    Send the OTP code to *email*.

    Delivery priority:
      1. AUTH_OTP_CONSOLE=true  → print to console (dev only)
      2. RESEND_API_KEY set     → Resend HTTP API (recommended for prod)
      3. OTP_EMAIL_PASSWORD set → plain SMTP (Office 365, Gmail, etc.)

    Returns (success: bool, message: str).
    """
    app_name = _cfg("OTP_APP_NAME", "Beisser Ops")
    subject  = f"Your {app_name} sign-in code"
    html     = _build_html(code, app_name)

    # 1. Dev console shortcut
    if os.environ.get("AUTH_OTP_CONSOLE", "").lower() in ("1", "true", "yes"):
        logger.info("DEV OTP for %s: %s", email, code)
        print(f"\n{'='*40}\nOTP for {email}: {code}\n{'='*40}\n", flush=True)
        return True, "console"

    # 2. Resend API
    if _cfg("RESEND_API_KEY"):
        return _send_via_resend(email, subject, html)

    # 3. SMTP fallback
    return _send_via_smtp(email, subject, html)
