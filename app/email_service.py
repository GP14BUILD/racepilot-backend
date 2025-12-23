import os
from typing import Optional
import httpx

# Email configuration from environment variables
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "RacePilot <info@race-pilot.app>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://race-pilot.app")

async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
):
    """
    Send an email using Resend API.

    For production: Set environment variable:
    - RESEND_API_KEY: Your Resend API key (get from https://resend.com)
    - FROM_EMAIL: Sender email (default: RacePilot <noreply@race-pilot.app>)
    """

    # If no Resend API key, log the email instead of sending
    if not RESEND_API_KEY:
        print(f"""
        ========== EMAIL (NOT SENT - NO RESEND API KEY) ==========
        To: {to_email}
        Subject: {subject}

        {text_content or html_content}
        ===========================================================
        """)
        return

    # Send email via Resend API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": FROM_EMAIL,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content,
                    "text": text_content or html_content,
                },
                timeout=10.0
            )

            if response.status_code != 200:
                error_detail = response.text
                print(f"Failed to send email to {to_email}: {error_detail}")
                raise Exception(f"Resend API error: {error_detail}")

            print(f"✅ Email sent successfully to {to_email}")
            return response.json()
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")
        # Don't raise - we don't want email failures to break registration
        return None


async def send_welcome_email(email: str, name: str, club_name: str):
    """Send welcome email to newly registered users"""

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
                background: linear-gradient(135deg, #1e40af, #3b82f6);
                color: white;
                padding: 40px 20px;
                text-align: center;
                border-radius: 10px 10px 0 0;
            }}
            .logo {{
                font-size: 48px;
                margin-bottom: 10px;
            }}
            .content {{
                background: #f8fafc;
                padding: 40px 30px;
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
            .features {{
                background: white;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .feature {{
                margin: 15px 0;
                padding-left: 30px;
                position: relative;
            }}
            .feature:before {{
                content: "⛵";
                position: absolute;
                left: 0;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                color: #64748b;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">⛵</div>
            <h1 style="margin: 0; font-size: 32px;">Welcome to RacePilot!</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Professional GPS Sailing Analytics</p>
        </div>
        <div class="content">
            <h2>Hi {name},</h2>
            <p>Welcome aboard! We're excited to have you join <strong>{club_name}</strong> on RacePilot.</p>

            <p>Your account is now active and ready to start tracking your sailing sessions. Here's what you can do:</p>

            <div class="features">
                <div class="feature">
                    <strong>Record Sessions:</strong> Download the mobile app and start capturing every tack, gybe, and mark rounding with 10Hz GPS precision
                </div>
                <div class="feature">
                    <strong>Automatic Analysis:</strong> Our AI system automatically detects maneuvers and provides personalized coaching insights
                </div>
                <div class="feature">
                    <strong>Fleet Comparison:</strong> Compare your sessions with club mates and learn from the fastest sailors
                </div>
                <div class="feature">
                    <strong>Race Replay:</strong> Watch your races back on the web dashboard and identify exactly where you gained or lost positions
                </div>
            </div>

            <p style="text-align: center;">
                <a href="{FRONTEND_URL}/dashboard" class="button">Go to Dashboard</a>
            </p>

            <p style="margin-top: 30px;"><strong>Next Steps:</strong></p>
            <ol>
                <li>Download the RacePilot mobile app from Google Play</li>
                <li>Sign in with your email: <strong>{email}</strong></li>
                <li>Mount your GPS on the mast and start sailing!</li>
                <li>View your sessions and analytics on the web dashboard</li>
            </ol>

            <p>If you have any questions or need help getting started, reply to this email or contact us at info@race-pilot.app.</p>

            <p>Fair winds and following seas,<br>
            <strong>The RacePilot Team</strong></p>
        </div>
        <div class="footer">
            <p>RacePilot - Professional Sailing Race Analysis</p>
            <p><a href="{FRONTEND_URL}" style="color: #3b82f6; text-decoration: none;">race-pilot.app</a> | <a href="mailto:info@race-pilot.app" style="color: #3b82f6; text-decoration: none;">info@race-pilot.app</a></p>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Welcome to RacePilot!

    Hi {name},

    Welcome aboard! We're excited to have you join {club_name} on RacePilot.

    Your account is now active and ready to start tracking your sailing sessions.

    What you can do:
    - Record Sessions: Download the mobile app and start capturing every tack, gybe, and mark rounding
    - Automatic Analysis: Our AI system detects maneuvers and provides coaching insights
    - Fleet Comparison: Compare your sessions with club mates
    - Race Replay: Watch your races back on the web dashboard

    Next Steps:
    1. Download the RacePilot mobile app from Google Play
    2. Sign in with your email: {email}
    3. Mount your GPS on the mast and start sailing!
    4. View your sessions and analytics at {FRONTEND_URL}/dashboard

    Need help? Contact us at info@race-pilot.app

    Fair winds and following seas,
    The RacePilot Team

    ---
    RacePilot - Professional Sailing Race Analysis
    race-pilot.app
    """

    await send_email(
        to_email=email,
        subject=f"Welcome to RacePilot, {name}! 🎉",
        html_content=html_content,
        text_content=text_content
    )


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
