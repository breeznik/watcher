import smtplib
from email.mime.text import MIMEText
from typing import List
from app.config import get_settings

settings = get_settings()


def send_email(to_emails: List[str], subject: str, body: str):
    if not settings.smtp_host or not settings.from_email:
        return  # Email not configured; fail silently for now.

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.from_email
    msg["To"] = ", ".join(to_emails)

    smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587)
    try:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.sendmail(settings.from_email, to_emails, msg.as_string())
    finally:
        smtp.quit()