"""Isolated OpenAI-compatible connectivity probe."""

import json
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LlmProviderError(RuntimeError):
    def __init__(self, detail: str, elapsed_ms: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.elapsed_ms = elapsed_ms


def test_chat(api_base: str, model_id: str, api_key: str) -> dict[str, object]:
    body = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": "Hi, this is a connectivity test. Reply with 'OK'."}],
            "max_tokens": 10,
            "temperature": 0.1,
            "stream": False,
        }
    ).encode()
    request = Request(
        api_base.rstrip("/") + "/chat/completions",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    started = monotonic()
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
        content = str(payload["choices"][0]["message"]["content"])
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
        elapsed_ms = int((monotonic() - started) * 1000)
        raise LlmProviderError(f"LLM connectivity failed: {type(exc).__name__}", elapsed_ms) from exc
    return {
        "status": "success",
        "message": "LLM connectivity test succeeded",
        "reply": content[:200],
        "elapsed_ms": int((monotonic() - started) * 1000),
    }
