from __future__ import annotations

from tools import verify_r2_12_c


def test_browser_resources_close_before_playwright_driver(monkeypatch) -> None:
    events: list[str] = []

    class Context:
        def close(self) -> None:
            events.append("context-close")

    class Browser:
        def new_context(self, **_kwargs):
            events.append("context-open")
            return Context()

        def close(self) -> None:
            events.append("browser-close")

    class Chromium:
        def launch(self, **_kwargs):
            events.append("browser-open")
            return Browser()

    class Manager:
        chromium = Chromium()

        def __enter__(self):
            events.append("driver-open")
            return self

        def __exit__(self, *_args) -> None:
            events.append("driver-close")

    monkeypatch.setattr(verify_r2_12_c, "sync_playwright", Manager)

    with verify_r2_12_c.managed_browser(headless=True):
        events.append("test-actions")

    assert events == [
        "driver-open",
        "browser-open",
        "context-open",
        "test-actions",
        "context-close",
        "browser-close",
        "driver-close",
    ]


def test_browser_failure_is_captured_before_context_shutdown(monkeypatch) -> None:
    events: list[str] = []

    class Context:
        def close(self) -> None:
            events.append("context-close")

    class Browser:
        def new_context(self, **_kwargs):
            return Context()

        def close(self) -> None:
            events.append("browser-close")

    class Chromium:
        def launch(self, **_kwargs):
            return Browser()

    class Manager:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            events.append("driver-close")

    monkeypatch.setattr(verify_r2_12_c, "sync_playwright", Manager)

    def capture(_exc, _context) -> None:
        events.append("failure-captured")

    try:
        with verify_r2_12_c.managed_browser(headless=True, on_error=capture):
            raise RuntimeError("UI assertion failed")
    except RuntimeError:
        pass

    assert events == ["failure-captured", "context-close", "browser-close", "driver-close"]
