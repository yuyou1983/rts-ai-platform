"""Tests for LLMClient — OpenAI-compatible API wrapper with retry and config."""
from __future__ import annotations

import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from agents.llm_client import (
    _DEFAULT_BACKOFF_BASE,
    _DEFAULT_BASE_URL,
    _DEFAULT_MAX_RETRIES,
    _DEFAULT_MODEL,
    _DEFAULT_TIMEOUT,
    LLMClient,
    LLMClientError,
    _RetryableError,
    _resolve_config,
    get_default_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(content="Hello!", tool_calls=None, usage=None):
    """Build a dict mimicking an OpenAI chat completion response."""
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls

    resp = {
        "choices": [
            {"index": 0, "message": message, "finish_reason": "stop"}
        ],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return resp


def _mock_urlopen(data: bytes, status: int = 200):
    """Return a MagicMock for urllib.request.urlopen that yields *data*."""
    resp = MagicMock()
    resp.read.return_value = data
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    # urllib.request.urlopen returns the response directly when no error
    return resp


# ---------------------------------------------------------------------------
# chat_completions — normal behaviour
# ---------------------------------------------------------------------------

class TestChatCompletions:
    """Test chat_completions with mocked HTTP layer."""

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_basic_chat(self, mock_urlopen):
        """Happy-path: returns normalized {content, tool_calls, usage}."""
        payload = _make_openai_response(content="Hi there")
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="test-key", base_url="https://api.test.com/v1")
        result = client.chat_completions(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result["content"] == "Hi there"
        assert result["tool_calls"] == []
        assert result["usage"]["total_tokens"] == 15

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_tool_calls_parsed(self, mock_urlopen):
        """Tool calls in the response are normalized correctly."""
        tc_raw = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "move_unit", "arguments": '{"x":1}'},
            }
        ]
        payload = _make_openai_response(content=None, tool_calls=tc_raw)
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="k", base_url="https://api.test.com/v1")
        result = client.chat_completions(messages=[{"role": "user", "content": "go"}])

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "move_unit"
        assert result["tool_calls"][0]["id"] == "call_123"

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_model_override(self, mock_urlopen):
        """Explicit model param overrides the default."""
        payload = _make_openai_response()
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="k", base_url="https://api.test.com/v1", default_model="default-model")
        client.chat_completions(messages=[{"role": "user", "content": "hi"}], model="custom-model")

        # Verify the request body was built with "custom-model"
        call_args = mock_urlopen.call_args
        req = call_args[0][0]  # urllib.request.Request object
        body = json.loads(req.data.decode())
        assert body["model"] == "custom-model"

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_authorization_header(self, mock_urlopen):
        """Bearer token is included when api_key is set."""
        payload = _make_openai_response()
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="secret-key", base_url="https://api.test.com/v1")
        client.chat_completions(messages=[{"role": "user", "content": "hi"}])

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer secret-key"

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_extra_body_merged(self, mock_urlopen):
        """extra_body keys are merged into the request JSON."""
        payload = _make_openai_response()
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="k", base_url="https://api.test.com/v1")
        client.chat_completions(
            messages=[{"role": "user", "content": "hi"}],
            extra_body={"stream": False, "custom_flag": True},
        )

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["stream"] is False
        assert body["custom_flag"] is True

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_response_format_sent(self, mock_urlopen):
        """response_format is included when provided."""
        payload = _make_openai_response()
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="k", base_url="https://api.test.com/v1")
        client.chat_completions(
            messages=[{"role": "user", "content": "hi"}],
            response_format={"type": "json_object"},
        )

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    """Test exponential-backoff retry on 429 / 5xx errors."""

    @patch("agents.llm_client.time.sleep")
    @patch("agents.llm_client.urllib.request.urlopen")
    def test_retry_on_429(self, mock_urlopen, mock_sleep):
        """429 triggers retry; eventually succeeds."""
        payload = _make_openai_response(content="retried")
        error_resp = urllib.error.HTTPError(
            url="https://api.test.com/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b"rate limited"),
        )

        # First call raises 429, second succeeds
        mock_urlopen.side_effect = [error_resp, _mock_urlopen(json.dumps(payload).encode())]

        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            max_retries=3, backoff_base=0.01,
        )
        result = client.chat_completions(messages=[{"role": "user", "content": "go"}])

        assert result["content"] == "retried"
        assert mock_urlopen.call_count == 2
        # Exponential backoff: 0.01 * 2^0 = 0.01
        mock_sleep.assert_called_once_with(0.01)

    @patch("agents.llm_client.time.sleep")
    @patch("agents.llm_client.urllib.request.urlopen")
    def test_retry_on_500(self, mock_urlopen, mock_sleep):
        """5xx triggers retry."""
        payload = _make_openai_response(content="ok after 500")
        error_resp = urllib.error.HTTPError(
            url="https://api.test.com/v1/chat/completions",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(b"server error"),
        )
        mock_urlopen.side_effect = [
            error_resp,
            _mock_urlopen(json.dumps(payload).encode()),
        ]

        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            max_retries=3, backoff_base=0.01,
        )
        result = client.chat_completions(messages=[{"role": "user", "content": "go"}])
        assert result["content"] == "ok after 500"

    @patch("agents.llm_client.time.sleep")
    @patch("agents.llm_client.urllib.request.urlopen")
    def test_exhausted_retries_raises(self, mock_urlopen, mock_sleep):
        """After max_retries exhausted, LLMClientError is raised."""
        error_resp = urllib.error.HTTPError(
            url="https://api.test.com/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b"rate limited"),
        )
        mock_urlopen.side_effect = [error_resp] * 3

        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            max_retries=3, backoff_base=0.01,
        )
        with pytest.raises(LLMClientError, match="retries exhausted"):
            client.chat_completions(messages=[{"role": "user", "content": "go"}])

        assert mock_urlopen.call_count == 3

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_non_retryable_4xx_raises_immediately(self, mock_urlopen):
        """400/403/404 should raise LLMClientError without retry."""
        error_resp = urllib.error.HTTPError(
            url="https://api.test.com/v1/chat/completions",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"error": "invalid"}'),
        )
        mock_urlopen.side_effect = [error_resp]

        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            max_retries=3, backoff_base=0.01,
        )
        with pytest.raises(LLMClientError, match="HTTP 400"):
            client.chat_completions(messages=[{"role": "user", "content": "go"}])

        # Should NOT have retried
        assert mock_urlopen.call_count == 1

    @patch("agents.llm_client.time.sleep")
    @patch("agents.llm_client.urllib.request.urlopen")
    def test_backoff_is_exponential(self, mock_urlopen, mock_sleep):
        """Sleep durations follow exponential backoff: base * 2^(attempt-1)."""
        error = urllib.error.HTTPError(
            url="x", code=429, msg="", hdrs=None,
            fp=io.BytesIO(b""),
        )
        payload = _make_openai_response()
        mock_urlopen.side_effect = [
            error, error,
            _mock_urlopen(json.dumps(payload).encode()),
        ]

        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            max_retries=3, backoff_base=1.0,
        )
        client.chat_completions(messages=[{"role": "user", "content": "go"}])

        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)   # attempt 1: 1.0 * 2^0
        mock_sleep.assert_any_call(2.0)   # attempt 2: 1.0 * 2^1


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestTimeout:
    """Test timeout handling."""

    @patch("agents.llm_client.time.sleep")
    @patch("agents.llm_client.urllib.request.urlopen")
    def test_timeout_raises_retryable(self, mock_urlopen, mock_sleep):
        """A TimeoutError should trigger retry, then raise LLMClientError when exhausted."""
        mock_urlopen.side_effect = TimeoutError("timed out")

        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            max_retries=2, backoff_base=0.001,
        )
        with pytest.raises(LLMClientError):
            client.chat_completions(messages=[{"role": "user", "content": "go"}])

    @patch("agents.llm_client.time.sleep")
    @patch("agents.llm_client.urllib.request.urlopen")
    def test_urlerror_raises_retryable(self, mock_urlopen, mock_sleep):
        """URLError (DNS / connection refused) should trigger retry."""
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            max_retries=2, backoff_base=0.001,
        )
        with pytest.raises(LLMClientError):
            client.chat_completions(messages=[{"role": "user", "content": "go"}])

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_timeout_value_passed(self, mock_urlopen):
        """The timeout kwarg is passed to urlopen."""
        payload = _make_openai_response()
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="k", base_url="https://api.test.com/v1", timeout=60)
        client.chat_completions(messages=[{"role": "user", "content": "hi"}])

        mock_urlopen.assert_called_once()
        # The timeout is the second positional arg or a keyword arg
        call_kwargs = mock_urlopen.call_args
        assert call_kwargs.kwargs.get("timeout") == 60 or call_kwargs[1].get("timeout") == 60 or \
               (len(call_kwargs.args) > 1 and call_kwargs.args[1] == 60)


# ---------------------------------------------------------------------------
# Invalid response
# ---------------------------------------------------------------------------

class TestInvalidResponse:
    """Test handling of malformed API responses."""

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_invalid_json_raises(self, mock_urlopen):
        """Non-JSON response body raises LLMClientError."""
        mock_urlopen.return_value = _mock_urlopen(b"this is not json")

        client = LLMClient(api_key="k", base_url="https://api.test.com/v1")
        with pytest.raises(LLMClientError, match="Invalid JSON"):
            client.chat_completions(messages=[{"role": "user", "content": "hi"}])

    @patch("agents.llm_client.urllib.request.urlopen")
    def test_empty_choices_returns_empty_content(self, mock_urlopen):
        """Response with no choices yields empty content and empty tool_calls."""
        payload = {"choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
        mock_urlopen.return_value = _mock_urlopen(json.dumps(payload).encode())

        client = LLMClient(api_key="k", base_url="https://api.test.com/v1")
        result = client.chat_completions(messages=[{"role": "user", "content": "hi"}])
        assert result["content"] == ""
        assert result["tool_calls"] == []


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

class TestConfigResolution:
    """Test _resolve_config priority: explicit > env > hermes > defaults."""

    def test_explicit_args_win(self):
        key, url = _resolve_config(api_key="explicit-key", base_url="https://explicit.com/v1")
        assert key == "explicit-key"
        assert url == "https://explicit.com/v1"

    def test_env_vars_used_when_no_explicit(self):
        with patch.dict(os.environ, {
            "RTAS_LLM_API_KEY": "env-key",
            "RTAS_LLM_BASE_URL": "https://env.com/v1",
        }):
            key, url = _resolve_config()
            assert key == "env-key"
            assert url == "https://env.com/v1"

    def test_explicit_overrides_env(self):
        with patch.dict(os.environ, {
            "RTAS_LLM_API_KEY": "env-key",
            "RTAS_LLM_BASE_URL": "https://env.com/v1",
        }):
            key, url = _resolve_config(api_key="explicit-key", base_url="https://explicit.com/v1")
            assert key == "explicit-key"
            assert url == "https://explicit.com/v1"

    def test_defaults_when_nothing_set(self):
        with patch.dict(os.environ, {}, clear=True):
            # Also mock _load_hermes_config to return empty
            with patch("agents.llm_client._load_hermes_config", return_value={}):
                key, url = _resolve_config()
                assert key == ""
                assert url == _DEFAULT_BASE_URL

    def test_trailing_slash_stripped(self):
        key, url = _resolve_config(base_url="https://api.test.com/v1/")
        assert not url.endswith("/")

    def test_hermes_config_used_as_fallback(self):
        hermes_cfg = {
            "custom_providers": [
                {
                    "name": "ksyun-mgw",
                    "models": ["glm-5.1"],
                    "api_key": "hermes-key",
                    "base_url": "https://ksyun.com/v1",
                }
            ]
        }
        with patch.dict(os.environ, {}, clear=True):
            with patch("agents.llm_client._load_hermes_config", return_value=hermes_cfg):
                key, url = _resolve_config()
                assert key == "hermes-key"
                assert url == "https://ksyun.com/v1"


# ---------------------------------------------------------------------------
# LLMClientError and _RetryableError
# ---------------------------------------------------------------------------

class TestExceptions:
    """Test custom exception classes."""

    def test_llm_client_error_is_exception(self):
        assert issubclass(LLMClientError, Exception)

    def test_retryable_error_is_exception(self):
        assert issubclass(_RetryableError, Exception)

    def test_llm_client_error_message(self):
        err = LLMClientError("HTTP 403: forbidden")
        assert str(err) == "HTTP 403: forbidden"


# ---------------------------------------------------------------------------
# LLMClient init
# ---------------------------------------------------------------------------

class TestLLMClientInit:
    """Test constructor behaviour."""

    def test_default_values(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("agents.llm_client._load_hermes_config", return_value={}):
                client = LLMClient()
                assert client.default_model == _DEFAULT_MODEL
                assert client.timeout == _DEFAULT_TIMEOUT
                assert client.max_retries == _DEFAULT_MAX_RETRIES
                assert client.backoff_base == _DEFAULT_BACKOFF_BASE
                assert client.base_url == _DEFAULT_BASE_URL

    def test_custom_values(self):
        client = LLMClient(
            api_key="k", base_url="https://api.test.com/v1",
            default_model="custom-model",
            timeout=60, max_retries=5, backoff_base=2.0,
        )
        assert client.default_model == "custom-model"
        assert client.timeout == 60
        assert client.max_retries == 5
        assert client.backoff_base == 2.0


# ---------------------------------------------------------------------------
# Singleton: get_default_client
# ---------------------------------------------------------------------------

class TestGetDefaultClient:
    """Test get_default_client() singleton pattern."""

    def setup_method(self):
        """Reset the global singleton before each test."""
        import agents.llm_client as mod
        mod._default_client = None

    def test_returns_llmclient(self):
        with patch.dict(os.environ, {"RTAS_LLM_API_KEY": "test"}, clear=False):
            client = get_default_client()
            assert isinstance(client, LLMClient)

    def test_singleton_identity(self):
        """Repeated calls return the same object."""
        with patch.dict(os.environ, {"RTAS_LLM_API_KEY": "test"}, clear=False):
            c1 = get_default_client()
            c2 = get_default_client()
            assert c1 is c2

    def test_reset_allows_new_instance(self):
        """After resetting the global, a new instance is created."""
        import agents.llm_client as mod
        with patch.dict(os.environ, {"RTAS_LLM_API_KEY": "test"}):
            c1 = get_default_client()
            mod._default_client = None
            c2 = get_default_client()
            assert c1 is not c2


# ---------------------------------------------------------------------------
# YAML subset parser
# ---------------------------------------------------------------------------

class TestYamlSubsetParser:
    """Test _parse_yaml_subset for hermes config fallback."""

    def test_simple_key_value(self):
        from agents.llm_client import _parse_yaml_subset
        result = _parse_yaml_subset("key: value\n")
        assert result == {"key": "value"}

    def test_nested_dict(self):
        from agents.llm_client import _parse_yaml_subset
        yaml_text = "parent:\n  child: hello\n"
        result = _parse_yaml_subset(yaml_text)
        assert result == {"parent": {"child": "hello"}}

    def test_list_of_strings(self):
        from agents.llm_client import _parse_yaml_subset
        yaml_text = "items:\n  - one\n  - two\n"
        result = _parse_yaml_subset(yaml_text)
        assert result == {"items": ["one", "two"]}

    def test_boolean_values(self):
        from agents.llm_client import _parse_yaml_subset
        result = _parse_yaml_subset("flag: true\nother: false\n")
        assert result["flag"] is True
        assert result["other"] is False

    def test_numeric_values(self):
        from agents.llm_client import _parse_yaml_subset
        result = _parse_yaml_subset("port: 8080\nratio: 3.14\n")
        assert result["port"] == 8080
        assert result["ratio"] == 3.14

    def test_quoted_strings(self):
        from agents.llm_client import _parse_yaml_subset
        result = _parse_yaml_subset('name: "hello world"\n')
        assert result["name"] == "hello world"

    def test_comments_ignored(self):
        from agents.llm_client import _parse_yaml_subset
        result = _parse_yaml_subset("# comment\nkey: val\n")
        assert result == {"key": "val"}

    def test_empty_input(self):
        from agents.llm_client import _parse_yaml_subset
        result = _parse_yaml_subset("")
        assert result == {}