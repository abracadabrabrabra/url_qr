import asyncio
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from config import get_settings
import aiosmtplib

settings = get_settings()


async def send_reset_code_email(email_to: str, reset_code: str) -> bool:

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Password Reset Code - {settings.app_name}"
        msg["From"] = settings.smtp_from
        msg["To"] = email_to
        msg["X-Priority"] = "3"

        text_content = f"""
        Hello!

        You requested to reset your password for {settings.app_name}.

        Your password reset code is: {reset_code}

        This code will expire in 15 minutes.

        If you didn't request this, please ignore this email.

        Best regards,
        {settings.app_name} Team
        """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .code {{ 
                    font-size: 32px; 
                    font-weight: bold; 
                    background-color: #f0f0f0; 
                    padding: 20px; 
                    font-family: monospace;
                    border-radius: 5px;
                    text-align: center;
                }}
                .warning {{ color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <h2>Password Reset Request</h2>
            <p>You requested to reset your password for <strong>{settings.app_name}</strong>.</p>
            <p>Your password reset code is:</p>
            <div class="code">{reset_code}</div>
            <p>This code will expire in <strong>15 minutes</strong>.</p>
            <div class="warning">
                Never share this code with anyone. Our support team will never ask for your verification code.
            </div>
            <p>Best regards,<br>{settings.app_name} Team</p>
        </body>
        </html>
        """

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )

        #print(f"DEBUG: Reset code email sent to {email_to}")
        return True

    except aiosmtplib.SMTPAuthenticationError as e:
        print(f"ERROR: SMTP authentication failed: {e}")
        print(f"Check SMTP_USER='{settings.smtp_user}' and SMTP_PASSWORD is correct")
        return False
    except aiosmtplib.SMTPException as e:
        print(f"ERROR: SMTP error occurred: {type(e).__name__}: {e}")
        return False
    except asyncio.TimeoutError:
        print(f"ERROR: SMTP connection timeout")
        return False
    except Exception as e:
        print(f"ERROR: Failed to send email: {type(e).__name__}: {e}")
        return False