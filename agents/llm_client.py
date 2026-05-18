"""LLM Client for ReactGameAgent — OpenAI-compatible API wrapper.

Zero external dependencies: uses only stdlib (urllib.request + json).
Provides:
  - chat_completions(): OpenAI /v1/chat/completions compatible call
  - Config from env vars (RTAS_LLM_API_KEY / RTAS_LLM_BASE_URL) or
    ~/.hermes/config.yaml (custom_providers)
  - Structured JSON output via response_format
  - Retry with exponential backoff (3 attempts)
  - 30-second request timeout

Usage:
    from agents.llm_client import LLMClient

    client = LLMClient()  # reads config automatically
    result = client.chat_completions(
        messages=[{"role": "user", "content": "Hello"}],
        model="glm-5.1",
    )
    # result = {"content": "...", "tool_calls": [...], "usage": {...}}
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "glm-5.1"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_TIMEOUT = 30          # seconds
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 1.0   # seconds


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_hermes_config() -> dict[str, Any]:
    """Load ~/.hermes/config.yaml.

    Tries ``import yaml`` first; falls back to a minimal hand-rolled YAML
    subset parser that covers the structures used by the hermes config.
    """
    config_path = Path.home() / ".hermes" / "config.yaml"
    if not config_path.is_file():
        return {}

    # Try real YAML parser first
    try:
        import yaml  # type: ignore[import-untyped]
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass

    # Minimal fallback parser
    try:
        with open(config_path) as f:
            text = f.read()
        return _parse_yaml_subset(text)
    except Exception:
        return {}


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    """Minimal YAML subset parser for hermes config.

    Handles the structures actually used:
    - top-level key: value
    - nested dicts via indentation
    - lists of strings (``- item``)
    - lists of dicts (``- name: ...`` followed by indented keys)
    """
    root: dict[str, Any] = {}
    # Stack of (indent_level, container_dict)
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
    current_list_key: str | None = None
    current_list: list[Any] | None = None

    def _current_container() -> dict[str, Any]:
        return stack[-1][1]

    def _strip_val(v: str) -> Any:
        v = v.strip()
        if not v:
            return None
        # Remove surrounding quotes
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            return v[1:-1]
        # Booleans
        if v.lower() == "true":
            return True
        if v.lower() == "false":
            return False
        # Numbers
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
        return v

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # Skip blanks / comments
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(stripped)

        # Pop stack to find parent at lower indent
        while stack and stack[-1][0] >= indent and len(stack) > 1:
            stack.pop()

        # List item
        if stripped.startswith("- "):
            rest = stripped[2:].strip()
            if current_list is not None and current_list_key is not None:
                if ":" in rest:
                    # Dict item in list
                    item: dict[str, Any] = {}
                    k, v = rest.split(":", 1)
                    item[k.strip()] = _strip_val(v) if v.strip() else None
                    current_list.append(item)
                    # Collect remaining keys for this dict item
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j]
                        nxt_stripped = nxt.lstrip()
                        nxt_indent = len(nxt) - len(nxt_stripped)
                        if nxt_indent <= indent:
                            break
                        if (nxt_stripped.startswith("- ")
                                or not nxt_stripped
                                or nxt_stripped.startswith("#")):
                            break
                        if ":" in nxt_stripped:
                            nk, nv = nxt_stripped.split(":", 1)
                            item[nk.strip()] = (
                                _strip_val(nv) if nv.strip() else None
                            )
                        j += 1
                    i = j
                    continue
                else:
                    current_list.append(_strip_val(rest))
            i += 1
            continue

        # Key-value
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val_str = val.strip()

            current_list_key = None
            current_list = None

            if val_str == "":
                # Could be empty, a nested dict, or a list on next lines
                if i + 1 < len(lines):
                    nxt = lines[i + 1]
                    nxt_stripped = nxt.lstrip()
                    nxt_indent = len(nxt) - len(nxt_stripped)
                    if nxt_indent > indent and nxt_stripped.startswith("- "):
                        # It's a list
                        new_list: list[Any] = []
                        _current_container()[key] = new_list
                        current_list_key = key
                        current_list = new_list
                    elif nxt_indent > indent:
                        # It's a nested dict
                        new_dict: dict[str, Any] = {}
                        _current_container()[key] = new_dict
                        stack.append((indent, new_dict))
                else:
                    _current_container()[key] = None
            else:
                _current_container()[key] = _strip_val(val_str)

        i += 1

    return root


def _resolve_config(
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str]:
    """Resolve (api_key, base_url) from env vars, explicit args, and config.

    Priority:
      1. Explicit arguments (api_key / base_url params)
      2. Environment variables: RTAS_LLM_API_KEY, RTAS_LLM_BASE_URL
      3. ~/.hermes/config.yaml → custom_providers (prefer ksyun-mgw / glm-5.1)
      4. Defaults
    """
    resolved_key = api_key
    resolved_url = base_url

    # 2. Env vars
    if not resolved_key:
        resolved_key = os.environ.get("RTAS_LLM_API_KEY")
    if not resolved_url:
        resolved_url = os.environ.get("RTAS_LLM_BASE_URL")

    # 3. Hermes config
    if not resolved_key or not resolved_url:
        cfg = _load_hermes_config()
        providers = cfg.get("custom_providers") or []
        for p in providers:
            if not isinstance(p, dict):
                continue
            models = p.get("models") or []
            name = p.get("name", "")
            if "glm-5.1" in models or name == "ksyun-mgw":
                if not resolved_key and p.get("api_key"):
                    resolved_key = p["api_key"]
                if not resolved_url and p.get("base_url"):
                    resolved_url = p["base_url"]
                break
        # Fallback: any provider with base_url
        if not resolved_url:
            for p in providers:
                if isinstance(p, dict) and p.get("base_url"):
                    resolved_url = p["base_url"]
                    break

    # 4. Defaults
    if not resolved_url:
        resolved_url = _DEFAULT_BASE_URL
    if not resolved_key:
        resolved_key = ""

    resolved_url = resolved_url.rstrip("/")

    return resolved_key, resolved_url


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMClientError(Exception):
    """Non-retryable LLM client error (4xx, invalid response, etc.)."""


class _RetryableError(Exception):
    """Internal: retryable error (429, 5xx, network issues, timeout)."""


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class LLMClient:
    """OpenAI-compatible LLM client using only stdlib.

    Parameters
    ----------
    api_key : str | None
        Bearer token. Falls back to RTAS_LLM_API_KEY env / hermes config.
    base_url : str | None
        API root, e.g. ``"http://10.69.93.80/v1"``.
        Falls back to RTAS_LLM_BASE_URL env / hermes config.
    default_model : str
        Model name sent in every request unless overridden.
        Defaults to ``"glm-5.1"``.
    timeout : int
        Per-request timeout in seconds.
    max_retries : int
        Number of attempts before giving up.
    backoff_base : float
        Base for exponential backoff (seconds).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = _DEFAULT_MODEL,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
    ) -> None:
        self.api_key, self.base_url = _resolve_config(api_key, base_url)
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

        if not self.api_key:
            logger.warning(
                "LLMClient: no API key configured — "
                "set RTAS_LLM_API_KEY env var or pass api_key="
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat_completions(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call OpenAI-compatible ``/v1/chat/completions``.

        Parameters
        ----------
        messages : list[dict]
            Chat messages, e.g.
            ``[{"role": "system", "content": "..."},
              {"role": "user", "content": "..."}]``.
        model : str | None
            Override default model.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Max tokens in the response.
        response_format : dict | None
            ``{"type": "json_object"}`` to request structured JSON output.
        tools : list[dict] | None
            Tool/function definitions for function calling.
        tool_choice : str | dict | None
            ``"auto"``, ``"none"``, or
            ``{"type": "function", "function": {"name": "..."}}``.
        extra_body : dict | None
            Extra top-level keys merged into the request body.

        Returns
        -------
        dict
            ``{"content": str, "tool_calls": list, "usage": dict}``

        Raises
        ------
        LLMClientError
            On non-retryable HTTP errors or after exhausting retries.
        """
        model = model or self.default_model

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format is not None:
            body["response_format"] = response_format
        if tools is not None:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if extra_body is not None:
            body.update(extra_body)

        return self._request_with_retry(
            method="POST",
            path="/chat/completions",
            body=body,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request_with_retry(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute HTTP request with exponential-backoff retry."""
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return self._do_request(method, path, body)
            except _RetryableError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    delay = self.backoff_base * (2 ** (attempt - 1))
                    logger.warning(
                        "LLMClient retry %d/%d after %s — sleeping %.1fs",
                        attempt, self.max_retries, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "LLMClient exhausted %d retries: %s",
                        self.max_retries, exc,
                    )
            except LLMClientError:
                raise  # non-retryable, propagate immediately

        raise LLMClientError(
            f"All {self.max_retries} retries exhausted"
        ) from last_exc

    def _do_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Single HTTP request to the API."""
        url = f"{self.base_url}{path}"

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(
            url, data=payload, headers=headers, method=method
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = ""
            try:
                raw = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            # Retry on 429 / 5xx
            if status == 429 or status >= 500:
                raise _RetryableError(
                    f"HTTP {status}: {raw[:500]}"
                ) from exc

            raise LLMClientError(
                f"HTTP {status}: {raw[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            # Network-level error (DNS, connection refused, timeout)
            raise _RetryableError(str(exc)) from exc
        except TimeoutError as exc:
            raise _RetryableError(
                f"Request timed out after {self.timeout}s"
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMClientError(
                f"Invalid JSON response: {raw[:500]}"
            ) from exc

        return self._parse_response(data)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> dict[str, Any]:
        """Normalize OpenAI chat completion response to our format.

        Returns
        -------
        dict
            ``{"content": str, "tool_calls": list, "usage": dict}``
        """
        choices = data.get("choices") or []
        content = ""
        tool_calls: list[dict[str, Any]] = []

        if choices:
            choice = choices[0]
            message = choice.get("message") or {}
            # Content may be None when tool_calls are present
            content = message.get("content") or ""
            # Tool calls
            raw_tc = message.get("tool_calls")
            if raw_tc:
                for tc in raw_tc:
                    func = tc.get("function") or {}
                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": func.get("name", ""),
                            "arguments": func.get("arguments", ""),
                        },
                    })

        usage_raw = data.get("usage") or {}
        usage = {
            "prompt_tokens": usage_raw.get("prompt_tokens", 0),
            "completion_tokens": usage_raw.get("completion_tokens", 0),
            "total_tokens": usage_raw.get("total_tokens", 0),
        }

        return {
            "content": content,
            "tool_calls": tool_calls,
            "usage": usage,
        }


# ---------------------------------------------------------------------------
# Convenience singleton
# ---------------------------------------------------------------------------

_default_client: LLMClient | None = None


def get_default_client() -> LLMClient:
    """Return a process-wide default :class:`LLMClient` (lazy-init)."""
    global _default_client  # noqa: PLW0603
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client