"""Gecko — simple concurrent web crawler with streaming support."""
from __future__ import annotations

import json
import time
from abc import ABC
from asyncio import Queue, TaskGroup, sleep, run as asyncio_run
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from gecko.fetcher import Response, AsyncSession

_SENTINEL = object()


@dataclass
class CrawlStats:
    pages_crawled: int = 0
    items_scraped: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    start_time: float = field(default_factory=time.monotonic)

    def finish(self) -> CrawlStats:
        self.duration_seconds = round(time.monotonic() - self.start_time, 2)
        return self


class Gecko(ABC):
    start_urls: list[str] = []
    concurrency: int = 4
    download_delay: float = 0.0
    max_pages: int = 0
    impersonate: str = "chrome131"

    def __init__(self):
        self.stats = CrawlStats()
        self._items: list[dict] = []
        self._seen: set[str] = set()

    def run(self) -> Gecko:
        asyncio_run(self._run())
        return self

    async def stream(self) -> AsyncIterator[dict]:
        """Run and yield items as they're scraped."""
        from anyio import create_memory_object_stream
        send, recv = create_memory_object_stream[dict](max_buffer_size=100)

        async def run_and_send():
            try:
                await self._crawl(send)
            finally:
                await send.aclose()

        async with TaskGroup() as tg:
            tg.create_task(run_and_send())
            async for item in recv:
                yield item

        self.stats.finish()

    async def _run(self) -> None:
        async for _ in self.stream():
            pass

    async def _crawl(self, item_send=None) -> None:
        queue: Queue = Queue()
        stopped = False

        for url in self.start_urls:
            self._seen.add(url)
            queue.put_nowait((url, self.parse))

        async def worker(session: AsyncSession):
            nonlocal stopped
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    queue.task_done()
                    return

                url, callback = item

                if stopped or (self.max_pages and self.stats.pages_crawled >= self.max_pages):
                    stopped = True
                    self.stats.skipped += 1
                    queue.task_done()
                    continue

                try:
                    response = await session.get(url)
                    self.stats.pages_crawled += 1
                except Exception:
                    self.stats.errors += 1
                    queue.task_done()
                    continue

                if self.download_delay:
                    await sleep(self.download_delay)

                if callback:
                    try:
                        for result in callback(response):
                            if isinstance(result, Request):
                                if result.url not in self._seen:
                                    self._seen.add(result.url)
                                    queue.put_nowait((result.url, result.callback))
                            elif isinstance(result, dict):
                                self._items.append(result)
                                self.stats.items_scraped += 1
                                if item_send is not None:
                                    await item_send.send(result)
                    except Exception:
                        self.stats.errors += 1

                queue.task_done()

        async with AsyncSession(impersonate=self.impersonate) as session:
            async with TaskGroup() as tg:
                tasks = [tg.create_task(worker(session)) for _ in range(self.concurrency)]
                await queue.join()
                for _ in tasks:
                    queue.put_nowait(_SENTINEL)

    @property
    def items(self) -> list[dict]:
        return self._items

    def save(self, path: str) -> int:
        with open(path, "w") as f:
            json.dump(self._items, f, indent=2, ensure_ascii=False)
        return len(self._items)

    def save_jsonl(self, path: str) -> int:
        with open(path, "w") as f:
            for item in self._items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return len(self._items)


class Request:
    __slots__ = ("url", "callback")

    def __init__(self, url: str, callback: Callable | None = None):
        self.url = url
        self.callback = callback


def _response_follow(self: Response, url: str, callback: Callable | None = None) -> Request:
    from urllib.parse import urljoin
    return Request(urljoin(self.url, url), callback=callback)


Response.follow = _response_follow  # type: ignore[attr-defined]
