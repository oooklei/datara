"""告警通道适配器：只有通道确认成功后，记录才允许进入 sent。"""

from email.message import EmailMessage
import json
import smtplib
from urllib import request

from common.config import Settings, get_settings


class DeliveryError(RuntimeError):
    """告警通道不支持、配置不完整或投递失败。"""


def _deliver_webhook(title: str, content: str, settings: Settings) -> None:
    if not settings.alert_webhook_url.strip():
        raise DeliveryError("ALERT_WEBHOOK_URL 未配置")
    payload = json.dumps({"title": title, "content": content}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        settings.alert_webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=settings.alert_delivery_timeout) as response:  # noqa: S310
            status = int(getattr(response, "status", 200))
    except OSError as exc:
        raise DeliveryError(f"webhook 投递失败: {exc}") from exc
    if not 200 <= status < 300:
        raise DeliveryError(f"webhook 返回 HTTP {status}")


def _deliver_email(title: str, content: str, settings: Settings) -> None:
    recipients = [item.strip() for item in settings.alert_email_to.split(",") if item.strip()]
    if not settings.smtp_host.strip() or not recipients:
        raise DeliveryError("SMTP_HOST 或 ALERT_EMAIL_TO 未配置")

    message = EmailMessage()
    message["Subject"] = title
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(recipients)
    message.set_content(content)
    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.alert_delivery_timeout,
        ) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_pwd)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise DeliveryError(f"邮件投递失败: {exc}") from exc


def deliver(
    channel: str | None,
    title: str | None,
    content: str | None,
    settings: Settings | None = None,
) -> None:
    """投递一条告警；失败时抛出 DeliveryError。"""
    cfg = settings or get_settings()
    selected = (channel or "system").strip().lower()
    subject = title or "Datara 告警"
    body = content or ""
    if selected in {"system", "站内"}:
        return
    if selected == "webhook":
        _deliver_webhook(subject, body, cfg)
        return
    if selected in {"email", "mail", "邮件"}:
        _deliver_email(subject, body, cfg)
        return
    raise DeliveryError(f"不支持的告警通道: {selected}")
