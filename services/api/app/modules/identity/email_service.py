from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger("jkr_api.identity.email_service")


def _build_otp_html(code: str, purpose: str) -> str:
    action_text = "sign up for your JKR AI Calling account" if purpose == "signup" else "log in to your JKR AI Calling workspace"
    title_text = "Verify your account" if purpose == "signup" else "Complete your login"

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title_text}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f17; color: #f1f5f9; padding: 40px 20px; margin: 0;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 520px; margin: 0 auto; background: #131b2e; border: 1px solid #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.4);">
    <tr>
      <td style="padding: 32px 32px 20px 32px; text-align: center; background: linear-gradient(135deg, rgba(234, 88, 12, 0.15) 0%, rgba(245, 158, 11, 0.05) 100%); border-bottom: 1px solid #1e293b;">
        <div style="display: inline-block; width: 48px; height: 48px; background: linear-gradient(135deg, #f59e0b, #d97706); border-radius: 12px; line-height: 48px; font-size: 24px; color: #000; font-weight: bold; margin-bottom: 12px;">⚡</div>
        <h1 style="color: #ffffff; font-size: 20px; margin: 0; font-weight: 700;">JKR AI Calling</h1>
        <p style="color: #94a3b8; font-size: 13px; margin: 6px 0 0 0;">India-first Real-Time Voice Platform</p>
      </td>
    </tr>
    <tr>
      <td style="padding: 32px;">
        <h2 style="color: #f8fafc; font-size: 18px; margin: 0 0 12px 0;">{title_text}</h2>
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">
          Use the following 6-digit verification code to {action_text}.
        </p>
        <div style="background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 24px;">
          <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #fbbf24; font-family: monospace;">{code}</span>
        </div>
        <p style="color: #94a3b8; font-size: 12px; line-height: 1.5; margin: 0 0 16px 0;">
          ⏳ <strong>This code expires in 10 minutes.</strong><br>
          If you did not request this verification, please ignore this email. No action is required.
        </p>
      </td>
    </tr>
    <tr>
      <td style="padding: 20px 32px; background: #0a0f1d; border-top: 1px solid #1e293b; text-align: center;">
        <p style="color: #64748b; font-size: 11px; margin: 0;">&copy; 2026 JKR AI Calling. All rights reserved.</p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_smtp_sync(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    host: str,
    port: int,
    user: str,
    password: str,
    from_email: str,
    from_name: str,
) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=10.0) as server:
            if user and password:
                server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=10.0) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except Exception:
                pass  # non-TLS SMTP fallback
            if user and password:
                server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
    return True


async def _send_resend_async(
    *,
    api_key: str,
    to_email: str,
    subject: str,
    html_body: str,
    from_email: str,
) -> bool:
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201):
            return True
        logger.error("[RESEND ERROR] Status %d: %s", resp.status_code, resp.text)
        return False


async def _send_brevo_async(
    *,
    api_key: str,
    sender_email: str,
    sender_name: str,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> tuple[bool, str]:
    """Dispatches a transactional email via Brevo REST API v3 (POST /v3/smtp/email).
    Returns (success: bool, error_message: str).
    """
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": api_key.strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "sender": {
            "name": sender_name.strip() if sender_name else "JKR AI Calling",
            "email": sender_email.strip(),
        },
        "to": [
            {
                "email": to_email.strip(),
            }
        ],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                    msg_id = data.get("messageId", "ok")
                except Exception:
                    msg_id = "ok"
                logger.info("[BREVO SUCCESS] Verification email sent to %s (messageId: %s)", to_email, msg_id)
                return True, ""

            # Parse error safely without logging any credentials
            err_detail = "Failed to deliver email"
            try:
                err_json = resp.json()
                msg = err_json.get("message") or err_json.get("code") or resp.text
                err_detail = str(msg)
            except Exception:
                err_detail = resp.text[:200]

            logger.error("[BREVO ERROR] Status %d: %s", resp.status_code, err_detail)

            # Handle 300/day free limit and rate limits gracefully
            if resp.status_code in (402, 429) or "quota" in err_detail.lower() or "credit" in err_detail.lower():
                return False, "Brevo daily sending limit reached (300 emails/day free tier). Please try again tomorrow or contact support."

            if resp.status_code == 401:
                return False, "Email authorization error. Please check your Brevo API key configuration."

            if "sender" in err_detail.lower():
                return False, f"Email sender verification issue: {err_detail}. Make sure BREVO_SENDER_EMAIL matches an authorized sender in Brevo."

            return False, f"Email delivery failed ({resp.status_code}): {err_detail}"

        except httpx.TimeoutException:
            logger.error("[BREVO TIMEOUT] Timed out sending email to %s", to_email)
            return False, "Email service timed out. Please try again."
        except Exception as exc:
            logger.error("[BREVO EXCEPTION] Failed to send email to %s: %s", to_email, exc)
            return False, f"Email service error: {exc}"


async def send_otp_email(to_email: str, code: str, purpose: str = "signup") -> tuple[bool, str]:
    """Dispatches a 6-digit OTP email to the user.

    Supports:
    1. Brevo REST API (v3) if BREVO_API_KEY is configured (recommended free tier provider, 300/day).
    2. Resend API if RESEND_API_KEY is configured.
    3. SMTP (e.g. Gmail SMTP with App Password, AWS SES) if SMTP_HOST is configured.
    4. Safe development fallback logging if no provider is configured yet.
    """
    subject = f"Your JKR AI Calling verification code: {code}"
    html_body = _build_otp_html(code, purpose)
    text_body = (
        f"Your JKR AI Calling verification code is: {code}\n\n"
        f"This code will expire in 10 minutes.\n"
        f"If you did not request this code, you can safely ignore this email."
    )

    # 1. Try Brevo API (primary transactional email provider)
    brevo_api_key = os.getenv("BREVO_API_KEY")
    if brevo_api_key:
        sender_email = (
            os.getenv("BREVO_SENDER_EMAIL")
            or os.getenv("SMTP_FROM_EMAIL")
            or os.getenv("RESEND_SANDBOX_OWNER")
            or "hemanth.t24@iiits.in"
        )
        sender_name = os.getenv("BREVO_SENDER_NAME", "JKR AI Calling")

        success, err_msg = await _send_brevo_async(
            api_key=brevo_api_key,
            sender_email=sender_email,
            sender_name=sender_name,
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
        if success:
            logger.info("[EMAIL OTP] Sent verification email via Brevo to %s", to_email)
            return True, ""
        return False, err_msg

    # 2. Try Resend
    resend_api_key = os.getenv("RESEND_API_KEY")
    if resend_api_key:
        from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
        try:
            success = await _send_resend_async(
                api_key=resend_api_key,
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                from_email=from_email,
            )
            if success:
                logger.info("[EMAIL OTP] Sent verification email via Resend to %s", to_email)
                return True, ""

            # If recipient is restricted by Resend sandbox, dispatch directly to developer account email
            sandbox_owner = os.getenv("RESEND_SANDBOX_OWNER", "hemanth.t24@iiits.in")
            if sandbox_owner and to_email.lower() != sandbox_owner.lower():
                logger.info("[EMAIL OTP] Resend sandbox restriction: dispatching OTP to owner %s", sandbox_owner)
                owner_html = f"""<div style="background:#1e293b;padding:12px;border-radius:8px;margin-bottom:16px;color:#f8fafc;font-size:13px;">
                <strong>Notice:</strong> This verification code was requested for <strong>{to_email}</strong>.
                Because your Resend account is currently in sandbox mode, the email has been routed to your registered developer inbox (<strong>{sandbox_owner}</strong>).
                </div>{html_body}"""
                await _send_resend_async(
                    api_key=resend_api_key,
                    to_email=sandbox_owner,
                    subject=f"[OTP for {to_email}] {subject}",
                    html_body=owner_html,
                    from_email=from_email,
                )
                return True, ""
            return False, "Failed to deliver email via Resend"
        except Exception as exc:
            logger.error("[EMAIL OTP RESEND ERROR] Failed to send to %s: %s", to_email, exc)
            return False, f"Resend error: {exc}"

    # 3. Try SMTP if configured
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        smtp_from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user or "noreply@jkr-calling.com")
        smtp_from_name = os.getenv("SMTP_FROM_NAME", "JKR AI Calling")

        try:
            await asyncio.to_thread(
                _send_smtp_sync,
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                host=smtp_host,
                port=smtp_port,
                user=smtp_user,
                password=smtp_password,
                from_email=smtp_from_email,
                from_name=smtp_from_name,
            )
            logger.info("[EMAIL OTP] Sent verification email via SMTP to %s", to_email)
            return True, ""
        except Exception as exc:
            logger.error("[EMAIL OTP SMTP ERROR] Failed to send to %s: %s", to_email, exc)
            return False, f"SMTP error: {exc}"

    # 4. Safe development / unconfigured provider fallback
    banner = (
        "\n" + "=" * 60 + "\n"
        f"[EMAIL OTP CODE DISPATCH]\n"
        f"  To:      {to_email}\n"
        f"  Purpose: {purpose}\n"
        f"  Code:    {code}\n"
        f"  Note:    Configure BREVO_API_KEY, SMTP_HOST, or RESEND_API_KEY to send real emails to inbox.\n"
        + "=" * 60 + "\n"
    )
    logger.info(banner)
    print(banner, flush=True)
    return True, ""
