from types import SimpleNamespace

import pytest

from alert import channels


def _settings(**overrides):
    values = {
        "alert_webhook_url": "", "alert_delivery_timeout": 3.0,
        "alert_email_to": "", "smtp_host": "", "smtp_port": 25,
        "smtp_user": "", "smtp_pwd": "", "smtp_from": "datara@example.test",
        "smtp_use_tls": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_system_delivery_is_the_persisted_notification() -> None:
    channels.deliver("system", "title", "content", _settings())


def test_webhook_requires_configuration() -> None:
    with pytest.raises(channels.DeliveryError, match="ALERT_WEBHOOK_URL"):
        channels.deliver("webhook", "title", "content", _settings())


def test_webhook_posts_json(monkeypatch) -> None:
    captured = {}

    class Response:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *_args): return None

    def fake_open(req, timeout):
        captured.update(url=req.full_url, body=req.data.decode("utf-8"), timeout=timeout)
        return Response()

    monkeypatch.setattr(channels.request, "urlopen", fake_open)
    channels.deliver("webhook", "任务失败", "boom", _settings(alert_webhook_url="https://alerts.example.test/hook"))
    assert captured == {
        "url": "https://alerts.example.test/hook",
        "body": '{"title": "任务失败", "content": "boom"}',
        "timeout": 3.0,
    }


def test_unknown_channel_is_an_explicit_failure() -> None:
    with pytest.raises(channels.DeliveryError, match="不支持"):
        channels.deliver("sms", "title", "content", _settings())
