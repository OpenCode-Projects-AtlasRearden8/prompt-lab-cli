"""Endpoint configuration, resolved from (in order): built-in defaults, the
library's config.json, environment variables, then command-line flags.

Prompt Lab deliberately has NO API key setting. It is built for local or
self-hosted OpenAI-compatible servers (Ollama, LM Studio, llama.cpp, vLLM...),
so there is nothing here worth leaking. If a config file or environment
variable tries to hand us a key, we refuse loudly instead of quietly
accepting it.
"""

import json
import os
from pathlib import Path

from .storage import StorageError

ENV_BASE_URL = "PROMPTLAB_BASE_URL"
ENV_MODEL = "PROMPTLAB_MODEL"
ENV_LIBRARY = "PROMPTLAB_LIBRARY"

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 60.0

DEFAULTS = {
    "base_url": DEFAULT_BASE_URL,
    "model": DEFAULT_MODEL,
    "temperature": DEFAULT_TEMPERATURE,
    "timeout": DEFAULT_TIMEOUT,
    "max_tokens": None,
    "system": None,
}

ENV_FIELDS = {
    "base_url": ENV_BASE_URL,
    "model": ENV_MODEL,
    "temperature": "PROMPTLAB_TEMPERATURE",
    "timeout": "PROMPTLAB_TIMEOUT",
    "max_tokens": "PROMPTLAB_MAX_TOKENS",
    "system": "PROMPTLAB_SYSTEM",
}


class ConfigError(StorageError):
    pass


def default_library_root():
    explicit = os.environ.get(ENV_LIBRARY)
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".promptlab"


def config_path(root):
    return Path(root) / "config.json"


def write_defaults(root):
    path = config_path(root)
    if path.is_file():
        return path
    path.write_text(
        json.dumps(
            {
                "base_url": DEFAULT_BASE_URL,
                "model": DEFAULT_MODEL,
                "temperature": DEFAULT_TEMPERATURE,
                "timeout": DEFAULT_TIMEOUT,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def load_config(root):
    cfg = dict(DEFAULTS)
    path = config_path(root)
    if path.is_file():
        file_cfg = _read_json(path)
        _reject_keys(file_cfg, "api_key", "apikey", "api-key", "authorization", source=str(path))
        for key in ("base_url", "model", "system"):
            if file_cfg.get(key) is not None:
                cfg[key] = str(file_cfg[key]).strip()
        if file_cfg.get("temperature") is not None:
            cfg["temperature"] = _as_number(file_cfg["temperature"], "temperature", str(path))
        if file_cfg.get("timeout") is not None:
            cfg["timeout"] = _as_number(file_cfg["timeout"], "timeout", str(path))
        if file_cfg.get("max_tokens") is not None:
            cfg["max_tokens"] = int(file_cfg["max_tokens"])

    for field, env_name in ENV_FIELDS.items():
        raw = os.environ.get(env_name)
        if raw and raw.strip():
            if field in ("temperature", "timeout"):
                cfg[field] = _as_number(raw, field, env_name)
            elif field == "max_tokens":
                cfg[field] = int(raw)
            else:
                cfg[field] = raw.strip()

    _reject_keys(os.environ, "PROMPTLAB_API_KEY", "PROMPTLAB_OPENAI_API_KEY", source="environment")
    cfg["base_url"], cfg["model"] = validate(cfg["base_url"], cfg["model"])
    return cfg


def validate(base_url, model):
    if not model or not str(model).strip():
        raise ConfigError(
            "No model is configured. Set 'model' in the library's config.json, "
            "or pass --model on the command line."
        )
    if not str(base_url).startswith(("http://", "https://")):
        raise ConfigError(
            f"The endpoint '{base_url}' is missing its scheme. Use something like "
            f"'{DEFAULT_BASE_URL}'."
        )
    return str(base_url).rstrip("/"), str(model).strip()


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc


def _reject_keys(mapping, *keys, source):
    present = [k for k in keys if mapping.get(k)]
    if present:
        raise ConfigError(
            f"Prompt Lab never uses API keys, so {', '.join(present)} in {source} "
            "is not supported. By design, nothing worth leaking goes in a config "
            "file. Point --base-url at a local OpenAI-compatible server (like "
            "Ollama) instead."
        )


def _as_number(value, name, source):
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} in {source} must be a number, got {value!r}.") from exc
