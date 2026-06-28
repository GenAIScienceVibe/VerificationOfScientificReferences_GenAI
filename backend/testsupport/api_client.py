from __future__ import annotations

import asyncio
from contextlib import ExitStack, asynccontextmanager
from typing import Any
from unittest.mock import patch

import httpx


async def _run_inline(func: Any, *args: Any, **kwargs: Any) -> Any:
    return func(*args, **kwargs)


@asynccontextmanager
async def _contextmanager_inline(cm: Any):
    value = cm.__enter__()
    try:
        yield value
    except Exception as exc:
        suppress = bool(cm.__exit__(type(exc), exc, exc.__traceback__))
        if not suppress:
            raise
    else:
        cm.__exit__(None, None, None)


class ApiTestClient:
    """Small httpx ASGI client for tests/scripts.

    The current sandbox's AnyIO threadpool blocks indefinitely. FastAPI uses
    that threadpool for sync endpoints and sync dependencies, so in-process
    validation patches those adapters to run inline while preserving the
    public request/response behavior needed by tests and demo scripts.
    """

    __test__ = False

    def __init__(self, app: Any, *, base_url: str = "http://testserver") -> None:
        self.app = app
        self.base_url = base_url

    def __enter__(self) -> "ApiTestClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return asyncio.run(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        with self._patch_threadpool_adapters():
            async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
                return await client.request(method, url, **kwargs)

    @staticmethod
    def _patch_threadpool_adapters() -> ExitStack:
        stack = ExitStack()
        targets = [
            "fastapi.routing.run_in_threadpool",
            "fastapi.dependencies.utils.run_in_threadpool",
            "fastapi.concurrency.run_in_threadpool",
            "starlette.concurrency.run_in_threadpool",
            "starlette.routing.run_in_threadpool",
            "starlette.datastructures.run_in_threadpool",
            "starlette._exception_handler.run_in_threadpool",
            "starlette.middleware.errors.run_in_threadpool",
            "starlette.endpoints.run_in_threadpool",
            "starlette.background.run_in_threadpool",
        ]
        for target in targets:
            stack.enter_context(patch(target, _run_inline))
        stack.enter_context(patch("fastapi.dependencies.utils.contextmanager_in_threadpool", _contextmanager_inline))
        stack.enter_context(patch("fastapi.concurrency.contextmanager_in_threadpool", _contextmanager_inline))
        return stack
