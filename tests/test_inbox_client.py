from __future__ import annotations

from collections import deque

import httpx
import pytest

from app.inbox import AvitoMessengerClient, AvitoMessengerClientError


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_get_chats_sends_auth_header_and_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer access-token"
        assert request.url.path == "/messenger/v2/accounts/1001/chats"
        assert request.url.params["item_ids"] == "10,20"
        assert request.url.params["unread_only"] == "true"
        assert request.url.params["chat_types"] == "u2i,u2u"
        assert request.url.params["limit"] == "50"
        assert request.url.params["offset"] == "10"
        return httpx.Response(
            200,
            json={"chats": [{"id": "chat-1"}, {"id": "chat-2"}]},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.avito.ru",
    ) as http_client:
        client = AvitoMessengerClient("access-token", client=http_client)
        chats = client.get_chats(
            1001,
            item_ids=[10, 20],
            unread_only=True,
            chat_types=["u2i", "u2u"],
            limit=50,
            offset=10,
        )

    assert tuple(chat["id"] for chat in chats) == ("chat-1", "chat-2")


def test_client_retries_on_rate_limit_with_retry_after() -> None:
    attempts = {"count": 0}
    fake_clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                429,
                headers={
                    "Retry-After": "2",
                    "X-RateLimit-Limit": "60",
                    "X-RateLimit-Remaining": "0",
                },
                text="too many requests",
            )
        return httpx.Response(
            200,
            json=[{"id": "message-1"}],
            headers={
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "59",
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.avito.ru",
    ) as http_client:
        client = AvitoMessengerClient(
            "access-token",
            client=http_client,
            sleep_func=fake_clock.sleep,
            clock_func=fake_clock.monotonic,
        )
        messages = client.get_messages(1001, "chat-1")

    assert attempts["count"] == 2
    assert fake_clock.sleeps == [2.0]
    assert tuple(message["id"] for message in messages) == ("message-1",)
    assert client.rate_limit is not None
    assert client.rate_limit.limit_per_minute == 60
    assert client.rate_limit.remaining == 59


def test_client_waits_before_next_request_when_rate_limit_budget_is_exhausted() -> None:
    fake_clock = FakeClock()
    responses = deque(
        [
            httpx.Response(
                200,
                json={"id": "chat-1"},
                headers={
                    "X-RateLimit-Limit": "60",
                    "X-RateLimit-Remaining": "0",
                },
            ),
            httpx.Response(
                200,
                json={"id": "chat-2"},
                headers={
                    "X-RateLimit-Limit": "60",
                    "X-RateLimit-Remaining": "58",
                },
            ),
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.popleft()

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.avito.ru",
    ) as http_client:
        client = AvitoMessengerClient(
            "access-token",
            client=http_client,
            sleep_func=fake_clock.sleep,
            clock_func=fake_clock.monotonic,
        )
        first_chat = client.get_chat(1001, "chat-1")
        second_chat = client.get_chat(1001, "chat-2")

    assert first_chat["id"] == "chat-1"
    assert second_chat["id"] == "chat-2"
    assert fake_clock.sleeps == [1.0]


def test_client_retries_on_server_error_and_raises_after_exhaustion() -> None:
    attempts = {"count": 0}
    fake_clock = FakeClock()

    def handler(_: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(502, text="bad gateway")

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.avito.ru",
    ) as http_client:
        client = AvitoMessengerClient(
            "access-token",
            client=http_client,
            max_retries=2,
            sleep_func=fake_clock.sleep,
            clock_func=fake_clock.monotonic,
        )
        with pytest.raises(AvitoMessengerClientError) as error:
            client.get_chat(1001, "chat-1")

    assert attempts["count"] == 3
    assert fake_clock.sleeps == [1.0, 2.0]
    assert error.value.status_code == 502
