import secrets
import string
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta


def generate_code() -> str:
    """Generate a 6-digit numeric code."""
    return "".join(secrets.choice(string.digits) for _ in range(6))


def send_code(user: dict, code: str, method: str = "email", smtp_config: dict = None) -> None:
    """
    Send 2FA code via the specified method.
    Falls back to console print if email is not configured or method is SMS.
    """
    if method == "email":
        if smtp_config and smtp_config.get("host"):
            try:
                _send_email(user["email"], code, smtp_config)
                return
            except Exception as exc:
                print(f"[2FA] Email send failed ({exc}), falling back to console.")
        # Console fallback for development
        print(f"\n{'=' * 40}")
        print(f"2FA CODE for {user['email']}: {code}")
        print(f"{'=' * 40}\n")
    elif method == "sms":
        # SMS requires an external service (e.g., Twilio). Console fallback.
        print(f"\n{'=' * 40}")
        print(f"2FA CODE (SMS) for {user.get('phone', 'unknown')}: {code}")
        print(f"{'=' * 40}\n")
    else:
        print(f"\n{'=' * 40}")
        print(f"2FA CODE ({method}) for {user.get('email', 'unknown')}: {code}")
        print(f"{'=' * 40}\n")


def _send_email(to_email: str, code: str, smtp_config: dict) -> None:
    """Send the verification code via SMTP."""
    body = (
        f"Your verification code is: {code}\n\n"
        "This code expires in 10 minutes.\n\n"
        "If you did not request this, please contact your tax preparer."
    )
    msg = MIMEText(body, "plain")
    msg["Subject"] = "Your Login Verification Code"
    msg["From"] = smtp_config.get("from", "noreply@taxportal.local")
    msg["To"] = to_email

    with smtplib.SMTP(smtp_config["host"], smtp_config.get("port", 587)) as server:
        if smtp_config.get("use_tls", True):
            server.starttls()
        if smtp_config.get("username"):
            server.login(smtp_config["username"], smtp_config["password"])
        server.send_message(msg)
