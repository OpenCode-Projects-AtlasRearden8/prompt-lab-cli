"""HTTP calls to an OpenAI-compatible chat endpoint.

The HTTP layer is plain urllib from the standard library. This module never
adds an Authorization header, because Prompt Lab does not handle API keys
at all.
"""

import json
import socket
import time
import urllib.error
import urllib.request

INPUT_PLACEHOLDER = "{{input}}"


def render(template, test_input):
    """Fill {{input}} in the template. Returns (rendered_text, used_placeholder)."""
    used = INPUT_PLACEHOLDER in template
    return template.replace(INPUT_PLACEHOLDER, test_input), used


def send_json(url, payload=None, method="POST", timeout=60.0):
    """Make an HTTP request; return (status, body_text). Network only."""
    data = None
    headers = {"Content-Type": "application/json", "User-Agent": "promptlab"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def chat(base_url, model, rendered_text, *, system=None, temperature=0.7,
         max_tokens=None, timeout=60.0):
    """Call /chat/completions. Returns {'ok': bool, 'content'|'error', 'latency': float}."""
    url = _chat_url(base_url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": rendered_text})
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    started = time.monotonic()
    try:
        _status, body = send_json(url, payload=payload, timeout=timeout)
        return {
            "ok": True,
            "content": _extract_content(body),
            "latency": time.monotonic() - started,
        }
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace").strip()[:500]
        except Exception:
            pass
        return {
            "ok": False,
            "error": f"The endpoint answered with HTTP {exc.code}. {detail}".strip(),
            "latency": time.monotonic() - started,
        }
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return {
            "ok": False,
            "error": f"Could not reach {url}: {reason}. Is the server running?",
            "latency": time.monotonic() - started,
        }
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        return {
            "ok": False,
            "error": f"Could not parse the endpoint's response: {exc}",
            "latency": time.monotonic() - started,
        }


def list_models(base_url, timeout=10.0):
    url = _models_url(base_url)
    _status, body = send_json(url, payload=None, method="GET", timeout=timeout)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{url} did not return JSON: {exc}") from exc
    items = data.get("data") if isinstance(data, dict) else data
    models = []
    for item in items or []:
        if isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))
        elif isinstance(item, str):
            models.append(item)
    return sorted(set(models))


def _chat_url(base_url):
    return str(base_url).rstrip("/") + "/chat/completions"


def _models_url(base_url):
    return str(base_url).rstrip("/") + "/models"


def _extract_content(body):
    data = json.loads(body)
    message = data["choices"][0]["message"]
    content = message.get("content") if isinstance(message, dict) else message
    return "" if content is None else str(content)
