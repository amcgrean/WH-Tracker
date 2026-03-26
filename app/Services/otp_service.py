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

def send_otp_email(email: str, code: str) -> tuple[bool, str]:
    """
    Send the OTP code to *email*.

    Returns (success: bool, message: str).
    In dev mode (AUTH_OTP_CONSOLE=true) prints to console instead.
    """
    # Dev mode shortcut
    if os.environ.get("AUTH_OTP_CONSOLE", "").lower() in ("1", "true", "yes"):
        logger.info("DEV OTP for %s: %s", email, code)
        print(f"\n{'='*40}\nOTP for {email}: {code}\n{'='*40}\n", flush=True)
        return True, "console"

    smtp_server = _cfg("OTP_SMTP_SERVER", _cfg("SMTP_SERVER", "smtp.office365.com"))
    smtp_port = int(_cfg("OTP_SMTP_PORT", _cfg("SMTP_PORT", "587")))
    smtp_user = _cfg("OTP_EMAIL_FROM", _cfg("EMAIL_ADDRESS"))
    smtp_pass = _cfg("OTP_EMAIL_PASSWORD", _cfg("EMAIL_PASSWORD"))
    from_addr = smtp_user or _cfg("OTP_EMAIL_FROM")

    if not smtp_user or not smtp_pass:
        logger.warning(
            "SMTP credentials not configured (OTP_EMAIL_FROM / OTP_EMAIL_PASSWORD). "
            "Set AUTH_OTP_CONSOLE=true for dev mode."
        )
        return False, "Email not configured."

    app_name = _cfg("OTP_APP_NAME", "Beisser Ops")
    subject = f"Your {app_name} sign-in code"

    html_body = f"""
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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [email], msg.as_string())
        return True, "sent"
    except smtplib.SMTPAuthenticationError:
        logger.error("OTP email: SMTP auth failed for user %s", smtp_user)
        return False, "SMTP authentication failed."
    except Exception as exc:
        logger.error("OTP email send failed: %s", exc)
        return False, f"Could not send email: {exc}"
