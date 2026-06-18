"""Minimal OpenAI-compatible chat client (stdlib only, no pip).

Used by demo.py to drive a real model through the compliance gate without
needing OpenCode installed. Reads keys from un/.env and falls back across
providers (DeepSeek / OpenAI / Gemini openai-compat) so the overnight demo
survives any one provider being out of credit.

This is demo plumbing — the audited deliverable is the hash chain in core.py,
which never touches the network.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def load_env(path: str | None = None) -> dict:
    path = path or os.path.join(ROOT, ".env")
    env: dict[str, str] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# provider order: cheap+reliable first, then fall back
PROVIDERS = [
    ("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "deepseek-chat"),
    ("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
     "GEMINI_API_KEY", "gemini-2.5-flash"),
]


class LLMError(Exception):
    pass


def _post(base: str, key: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(messages: list, tools: list | None = None, temperature: float = 0.0):
    """Return (assistant_message_dict, provider_name). Iterates providers
    until one succeeds; raises LLMError if all fail."""
    env = load_env()
    forced = os.environ.get("COMPLIANCE_LLM")
    order = [p for p in PROVIDERS if not forced or p[0] == forced]
    errors = []
    for name, base, keyname, model in order:
        key = env.get(keyname) or os.environ.get(keyname)
        if not key:
            errors.append(f"{name}: no key")
            continue
        body = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        try:
            data = _post(base, key, body)
            return data["choices"][0]["message"], f"{name}:{model}"
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            errors.append(f"{name}: HTTP {e.code} {detail}")
        except Exception as e:  # network/timeout/parse
            errors.append(f"{name}: {type(e).__name__} {e}")
    raise LLMError("all providers failed:\n  " + "\n  ".join(errors))
