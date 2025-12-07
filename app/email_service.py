import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from typing import Optional

# Email configuration from environment variables
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
):
    """
    Send an email using SMTP.

    For production: Set environment variables:
    - SMTP_HOST: SMTP server (e.g., smtp.gmail.com)
    - SMTP_PORT: SMTP port (587 for TLS)
    - SMTP_USER: Email username
    - SMTP_PASSWORD: Email password or app password
    - FROM_EMAIL: Sender email address
    """

    # If no SMTP credentials, log the email instead of sending
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"""
        ========== EMAIL (NOT SENT - NO SMTP CONFIG) ==========
        To: {to_email}
        Subject: {subject}

        {text_content or html_content}
        ========================================================
        """)
        return

    # Create message
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = FROM_EMAIL
    message["To"] = to_email

    # Add text and HTML parts
    if text_content:
        part1 = MIMEText(text_content, "plain")
        message.attach(part1)

    part2 = MIMEText(html_content, "html")
    message.attach(part2)

    # Send email
    try:
        await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        raise


async def send_password_reset_email(email: str, reset_token: str):
    """Send password reset email with token link"""

    reset_url = f"{FRONTEND_URL}/reset-password?token={reset_token}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: #1e40af;
                color: white;
                padding: 30px 20px;
                text-align: center;
                border-radius: 10px 10px 0 0;
            }}
            .content {{
                background: #f8fafc;
                padding: 30px;
                border-radius: 0 0 10px 10px;
            }}
            .button {{
                display: inline-block;
                background: #3b82f6;
                color: white;
                padding: 14px 30px;
                text-decoration: none;
                border-radius: 8px;
                margin: 20px 0;
                font-weight: bold;
            }}
            .footer {{
                text-align: center;
                margin-top: 20px;
                color: #64748b;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>⛵ RacePilot</h1>
            <p>Password Reset Request</p>
        </div>
        <div class="content">
            <h2>Reset Your Password</h2>
            <p>We received a request to reset your password. Click the button below to create a new password:</p>

            <a href="{reset_url}" class="button">Reset Password</a>

            <p><strong>This link will expire in 1 hour.</strong></p>

            <p>If you didn't request this password reset, you can safely ignore this email. Your password will not be changed.</p>

            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #64748b;">{reset_url}</p>
        </div>
        <div class="footer">
            <p>RacePilot - Professional Sailing Race Analysis</p>
            <p>This is an automated email, please do not reply.</p>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    RacePilot - Password Reset Request

    We received a request to reset your password.

    Click this link to reset your password:
    {reset_url}

    This link will expire in 1 hour.

    If you didn't request this password reset, you can safely ignore this email.

    ---
    RacePilot - Professional Sailing Race Analysis
    """

    await send_email(
        to_email=email,
        subject="Reset Your RacePilot Password",
        html_content=html_content,
        text_content=text_content
    )
