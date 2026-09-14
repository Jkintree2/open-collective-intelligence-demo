"""One provider preflight call. Prints capability results, never credentials."""

import json
import time

import httpx

from app.config import load_settings


def main() -> int:
    settings = load_settings()
    if not settings.llm_api_key:
        print("LLM_API_KEY is not configured. Provider preflight has not been run.")
        return 2
    body = {"model": settings.llm_model, "messages": [{"role": "user", "content": 'Return only this json object: {"ok":true}'}],
            "response_format": {"type": "json_object"}, "temperature": 0.1, "max_tokens": 100}
    if "deepseek" in settings.llm_base_url.lower():
        body["thinking"] = {"type": "disabled"}
    started = time.perf_counter()
    try:
        response = httpx.post(settings.llm_base_url.rstrip("/") + "/chat/completions", json=body,
                              headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                              timeout=httpx.Timeout(25, connect=5))
        print(json.dumps({"http": response.status_code, "model_requested": settings.llm_model,
                          "thinking_disabled_sent": "thinking" in body, "temperature_sent": 0.1,
                          "latency_ms": round((time.perf_counter() - started) * 1000)}))
        if response.status_code != 200:
            return 1
        data = response.json()
        content = json.loads(data["choices"][0]["message"]["content"])
        print(json.dumps({"model_returned": data.get("model"), "json_content": isinstance(content, dict),
                          "expected_object": content == {"ok": True}}))
        return 0 if content == {"ok": True} else 1
    except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"Preflight failed: {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
