"""HTTP client for the Avito Messenger API."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
import time
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://api.avito.ru"


@dataclass(frozen=True, slots=True)
class AvitoRateLimitState:
    """Rate-limit information returned by Avito response headers."""

    limit_per_minute: int | None = None
    remaining: int | None = None


class AvitoMessengerClientError(RuntimeError):
    """Raised when Avito Messenger API requests fail."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.response_body = response_body


class AvitoMessengerClient:
    """Thin Avito Messenger API client with retry and rate-limit handling."""

    def __init__(
        self,
        access_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        client: httpx.Client | None = None,
        sleep_func: Callable[[float], None] | None = None,
        clock_func: Callable[[], float] | None = None,
    ):
        self._access_token = self._normalize_access_token(access_token)
        self._base_url = self._normalize_base_url(base_url)
        self._max_retries = self._normalize_non_negative_int(max_retries, field="max_retries")
        self._backoff_factor = self._normalize_positive_float(
            backoff_factor,
            field="backoff_factor",
        )
        self._sleep = sleep_func or time.sleep
        self._clock = clock_func or time.monotonic
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)
        self._rate_limit: AvitoRateLimitState | None = None
        self._blocked_until_monotonic = 0.0

    @property
    def rate_limit(self) -> AvitoRateLimitState | None:
        """Return the latest known rate-limit state."""
        return self._rate_limit

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> AvitoMessengerClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def get_chats(
        self,
        user_id: str | int,
        *,
        item_ids: Iterable[str | int] | None = None,
        unread_only: bool | None = None,
        chat_types: Iterable[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[dict[str, Any], ...]:
        """Fetch chat list for one Avito account."""
        payload = self._request_json(
            "GET",
            f"/messenger/v2/accounts/{self._normalize_path_value(user_id, field='user_id')}/chats",
            params={
                "item_ids": self._normalize_csv(item_ids, field="item_ids"),
                "unread_only": self._normalize_optional_bool(unread_only),
                "chat_types": self._normalize_chat_types(chat_types),
                "limit": self._normalize_limit(limit),
                "offset": self._normalize_offset(offset),
            },
        )
        if not isinstance(payload, dict):
            raise AvitoMessengerClientError(
                "invalid_response",
                "Chat list response must be a JSON object.",
            )
        chats = payload.get("chats")
        if not isinstance(chats, list):
            raise AvitoMessengerClientError(
                "invalid_response",
                "Chat list response must contain a 'chats' array.",
            )
        return tuple(self._expect_object(chat, field="chats[]") for chat in chats)

    def get_chat(
        self,
        user_id: str | int,
        chat_id: str,
    ) -> dict[str, Any]:
        """Fetch one chat and its last message."""
        payload = self._request_json(
            "GET",
            (
                f"/messenger/v2/accounts/{self._normalize_path_value(user_id, field='user_id')}"
                f"/chats/{self._normalize_path_value(chat_id, field='chat_id')}"
            ),
        )
        return self._expect_object(payload, field="chat")

    def get_messages(
        self,
        user_id: str | int,
        chat_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[dict[str, Any], ...]:
        """Fetch message list for one chat."""
        payload = self._request_json(
            "GET",
            (
                f"/messenger/v3/accounts/{self._normalize_path_value(user_id, field='user_id')}"
                f"/chats/{self._normalize_path_value(chat_id, field='chat_id')}/messages/"
            ),
            params={
                "limit": self._normalize_limit(limit),
                "offset": self._normalize_offset(offset),
            },
        )
        if not isinstance(payload, list):
            raise AvitoMessengerClientError(
                "invalid_response",
                "Message list response must be a JSON array.",
            )
        return tuple(self._expect_object(message, field="messages[]") for message in payload)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        cleaned_params = self._clean_params(params)
        attempt = 0

        while True:
            self._wait_for_rate_limit()
            try:
                response = self._client.request(
                    method=method,
                    url=f"{self._base_url}{path}",
                    params=cleaned_params,
                    headers={
                        "Accept": "application/json",
                        "Authorization": self._access_token,
                    },
                )
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise AvitoMessengerClientError(
                        "network_error",
                        f"Avito request failed after retries: {exc}",
                    ) from exc
                self._sleep(self._backoff_delay(attempt))
                attempt += 1
                continue

            self._update_rate_limit(response)

            if response.status_code == 429:
                if attempt >= self._max_retries:
                    self._raise_for_response(response)
                delay = self._retry_delay(response, attempt)
                self._blocked_until_monotonic = max(
                    self._blocked_until_monotonic,
                    self._clock() + delay,
                )
                self._sleep(delay)
                attempt += 1
                continue

            if 500 <= response.status_code < 600:
                if attempt >= self._max_retries:
                    self._raise_for_response(response)
                self._sleep(self._backoff_delay(attempt))
                attempt += 1
                continue

            if response.is_error:
                self._raise_for_response(response)

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise AvitoMessengerClientError(
                    "invalid_json",
                    "Avito response is not valid JSON.",
                    status_code=response.status_code,
                    response_body=response.text,
                ) from exc

            if not isinstance(payload, (dict, list)):
                raise AvitoMessengerClientError(
                    "invalid_response",
                    "Avito response JSON must be an object or array.",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            return payload

    def _wait_for_rate_limit(self) -> None:
        now = self._clock()
        if self._blocked_until_monotonic <= now:
            return
        self._sleep(self._blocked_until_monotonic - now)

    def _update_rate_limit(self, response: httpx.Response) -> None:
        limit = self._parse_header_int(response.headers.get("X-RateLimit-Limit"))
        remaining = self._parse_header_int(response.headers.get("X-RateLimit-Remaining"))
        if limit is None and remaining is None:
            return

        self._rate_limit = AvitoRateLimitState(
            limit_per_minute=limit,
            remaining=remaining,
        )
        now = self._clock()

        if limit is not None and remaining == 0:
            self._blocked_until_monotonic = max(
                self._blocked_until_monotonic,
                now + max(1.0, 60.0 / limit),
            )
            return

        self._blocked_until_monotonic = min(self._blocked_until_monotonic, now)

    def _raise_for_response(self, response: httpx.Response) -> None:
        raise AvitoMessengerClientError(
            "http_error",
            (
                f"Avito request failed with status {response.status_code}: "
                f"{response.text[:500]}"
            ),
            status_code=response.status_code,
            response_body=response.text,
        )

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        parsed_retry_after = self._parse_retry_after(retry_after)
        if parsed_retry_after is not None:
            return parsed_retry_after
        return self._backoff_delay(attempt)

    def _backoff_delay(self, attempt: int) -> float:
        return self._backoff_factor * (2**attempt)

    @staticmethod
    def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        return {
            key: value
            for key, value in params.items()
            if value is not None
        }

    @staticmethod
    def _expect_object(value: Any, *, field: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise AvitoMessengerClientError(
                "invalid_response",
                f"{field} entry must be a JSON object.",
            )
        return dict(value)

    @staticmethod
    def _normalize_access_token(access_token: str) -> str:
        normalized = access_token.strip()
        if not normalized:
            raise AvitoMessengerClientError(
                "access_token_invalid",
                "access_token must not be empty.",
            )
        if normalized.lower().startswith("bearer "):
            return normalized
        return f"Bearer {normalized}"

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise AvitoMessengerClientError(
                "base_url_invalid",
                "base_url must not be empty.",
            )
        return normalized

    @staticmethod
    def _normalize_path_value(value: str | int, *, field: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise AvitoMessengerClientError(
                f"{field}_invalid",
                f"{field} must not be empty.",
            )
        return normalized

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        normalized = AvitoMessengerClient._normalize_non_negative_int(limit, field="limit")
        if normalized < 1 or normalized > 100:
            raise AvitoMessengerClientError(
                "limit_invalid",
                "limit must be between 1 and 100.",
            )
        return normalized

    @staticmethod
    def _normalize_offset(offset: int) -> int:
        normalized = AvitoMessengerClient._normalize_non_negative_int(offset, field="offset")
        if normalized > 1000:
            raise AvitoMessengerClientError(
                "offset_invalid",
                "offset must be between 0 and 1000.",
            )
        return normalized

    @staticmethod
    def _normalize_non_negative_int(value: int, *, field: str) -> int:
        if value < 0:
            raise AvitoMessengerClientError(
                f"{field}_invalid",
                f"{field} must be greater than or equal to zero.",
            )
        return value

    @staticmethod
    def _normalize_positive_float(value: float, *, field: str) -> float:
        if value <= 0:
            raise AvitoMessengerClientError(
                f"{field}_invalid",
                f"{field} must be greater than zero.",
            )
        return value

    @staticmethod
    def _normalize_optional_bool(value: bool | None) -> str | None:
        if value is None:
            return None
        return "true" if value else "false"

    @staticmethod
    def _normalize_csv(
        values: Iterable[str | int] | None,
        *,
        field: str,
    ) -> str | None:
        if values is None:
            return None
        normalized_values = []
        for value in values:
            normalized = str(value).strip()
            if not normalized:
                raise AvitoMessengerClientError(
                    f"{field}_invalid",
                    f"{field} must not contain empty values.",
                )
            normalized_values.append(normalized)
        if not normalized_values:
            return None
        return ",".join(normalized_values)

    @staticmethod
    def _normalize_chat_types(chat_types: Iterable[str] | None) -> str | None:
        if chat_types is None:
            return None
        allowed_values = {"u2i", "u2u"}
        normalized_values = []
        for chat_type in chat_types:
            normalized = str(chat_type).strip()
            if normalized not in allowed_values:
                raise AvitoMessengerClientError(
                    "chat_types_invalid",
                    "chat_types must contain only 'u2i' or 'u2u'.",
                )
            normalized_values.append(normalized)
        if not normalized_values:
            return None
        return ",".join(normalized_values)

    @staticmethod
    def _parse_header_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None

        try:
            parsed_seconds = float(value)
        except ValueError:
            parsed_seconds = None
        if parsed_seconds is not None:
            return max(0.0, parsed_seconds)

        try:
            parsed_datetime = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None

        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(tzinfo=UTC)
        delay = (parsed_datetime - datetime.now(UTC)).total_seconds()
        return max(0.0, delay)
