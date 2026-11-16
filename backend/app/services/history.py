"""Carga paginada e cache curta de klines Spot, sob demanda."""

import asyncio
import time
from datetime import datetime, timezone

from ..models import CandlePage, MarketInterval


class MarketHistoryCache:
    PAGE_LIMIT = 500
    MAX_PAGE_ENTRIES = 64
    MAX_EARLIEST_ENTRIES = 128

    def __init__(self, ttl_seconds: float = 60):
        self.ttl_seconds = ttl_seconds
        self._pages: dict[tuple[str, MarketInterval, int | None], tuple[float, CandlePage]] = {}
        self._earliest: dict[tuple[str, MarketInterval], tuple[float, int | None]] = {}
        self._lock = asyncio.Lock()

    async def get_page(self, client, pair: str, interval: MarketInterval, end_time: int | None = None) -> CandlePage:
        key = (pair, interval, end_time)
        pair_key = (pair, interval)
        async with self._lock:
            now = time.monotonic()
            cached = self._pages.get(key)
            earliest_cache = self._earliest.get(pair_key)
            if cached and cached[0] > now and earliest_cache and earliest_cache[0] > now:
                return cached[1]

            need_earliest = not earliest_cache or earliest_cache[0] <= now
            if need_earliest:
                page_rows, earliest_rows = await asyncio.gather(
                    client.klines(pair, interval, end_time=end_time, limit=self.PAGE_LIMIT),
                    client.klines(pair, interval, start_time=0, limit=1),
                )
                earliest = earliest_rows[0].open_time if earliest_rows else None
                self._earliest[pair_key] = (time.monotonic() + self.ttl_seconds, earliest)
            else:
                page_rows = await client.klines(pair, interval, end_time=end_time, limit=self.PAGE_LIMIT)
                earliest = earliest_cache[1]

            candles_by_time = {candle.open_time: candle for candle in page_rows}
            candles = [candles_by_time[open_time] for open_time in sorted(candles_by_time)]
            oldest = candles[0].open_time if candles else None
            latest = candles[-1].open_time if candles else None
            response = CandlePage(
                pair=pair,
                interval=interval,
                candles=candles,
                earliest_open_time=earliest,
                oldest_open_time=oldest,
                latest_open_time=latest,
                has_older=oldest is not None and earliest is not None and oldest > earliest,
                updated_at=datetime.now(timezone.utc),
            )
            expires = time.monotonic() + self.ttl_seconds
            self._pages[key] = (expires, response)
            self._prune(time.monotonic())
            return response

    def _prune(self, now: float) -> None:
        for key, (expires, _page) in list(self._pages.items()):
            if expires <= now:
                self._pages.pop(key, None)
        for key, (expires, _time) in list(self._earliest.items()):
            if expires <= now:
                self._earliest.pop(key, None)
        while len(self._pages) > self.MAX_PAGE_ENTRIES:
            oldest = min(self._pages, key=lambda key: self._pages[key][0])
            self._pages.pop(oldest, None)
        while len(self._earliest) > self.MAX_EARLIEST_ENTRIES:
            oldest = min(self._earliest, key=lambda key: self._earliest[key][0])
            self._earliest.pop(oldest, None)
