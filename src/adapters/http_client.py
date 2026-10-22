"""
src/adapters/http_client.py

Resilient HTTP client wrapper for outbound geocoding and mapping calls.
Features:
- Configurable timeout (default 5s)
- Max 2 retries with exponential backoff on 5xx and network errors only
- Descriptive User-Agent
- In-memory LRU cache keyed by normalized URL/query
- Simple rate limiter
"""

import asyncio
import time
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import httpx
from ..config import USER_AGENT


class LRUCache:
    def __init__(self, capacity: int = 256):
        self.capacity = capacity
        self.cache: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            # Move to end
            val = self.cache.pop(key)
            self.cache[key] = val
            return val
        return None

    def set(self, key: str, value: Any):
        if key in self.cache:
            self.cache.pop(key)
        elif len(self.cache) >= self.capacity:
            oldest = next(iter(self.cache))
            del self.cache[oldest]
        self.cache[key] = value


class ResilientHttpClient:
    def __init__(self, timeout_sec: float = 5.0, max_retries: int = 2, min_interval_sec: float = 1.0):
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.min_interval_sec = min_interval_sec
        self.last_request_time = 0.0
        self.cache = LRUCache(capacity=256)
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=self.timeout_sec
        )

    async def _rate_limit(self):
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval_sec:
            await asyncio.sleep(self.min_interval_sec - elapsed)
        self.last_request_time = time.monotonic()

    async def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        cache_key = url
        if params:
            cache_key += "?" + urlencode(sorted(params.items()))

        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        attempt = 0
        backoff = 0.5
        while attempt <= self.max_retries:
            await self._rate_limit()
            attempt += 1
            try:
                resp = await self.client.get(url, params=params)
                if resp.status_code >= 500:
                    if attempt <= self.max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                data = resp.json()
                self.cache.set(cache_key, data)
                return data
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt <= self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise e

    async def close(self):
        await self.client.aclose()


# Global client instance
default_http_client = ResilientHttpClient()
