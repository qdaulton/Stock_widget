import json
import os
import time
from typing import List, Optional

from fastapi.encoders import jsonable_encoder

from models import StockPrice

try:
    import redis  # type: ignore
except ImportError:  # redis optional for local runs
    redis = None


class PriceCache:
    """
    Tiny abstraction over Redis (with in-memory fallback) to cache a snapshot
    of the latest stock prices.

    We store a single key that contains:
        {"ts": <unix_epoch>, "data": [ StockPrice as dict ... ]}
    """

    def __init__(self, redis_url: Optional[str] = None, key: str = "prices:snapshot"):
        self.key = key
        self._local_cache: Optional[dict] = None

        redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._client = None

        if redis is not None:
            try:
                self._client = redis.Redis.from_url(redis_url, decode_responses=True)
                self._client.ping()
                print(f"[cache] Using Redis cache at {redis_url}")
            except Exception as e:
                print(f"[cache] Failed to connect to Redis ({e}); falling back to in-memory cache.")
                self._client = None
        else:
            print("[cache] redis package not installed; using in-memory cache only.")

    # ----------------- public API -----------------

    def set_snapshot(self, prices: List[StockPrice]) -> None:
        payload = {
            "ts": time.time(),
            "data": jsonable_encoder(prices),
        }
        blob = json.dumps(payload)

        if self._client is not None:
            try:
                # small TTL, after that it is treated as a miss
                self._client.set(self.key, blob, ex=60)
                return
            except Exception as e:
                print(f"[cache] Redis set failed, falling back to local cache: {e}")

        # local fallback
        self._local_cache = payload

    def get_snapshot(self, max_age_seconds: int = 15) -> Optional[List[StockPrice]]:
        # First try Redis
        raw = None
        if self._client is not None:
            try:
                raw = self._client.get(self.key)
            except Exception as e:
                print(f"[cache] Redis get failed, falling back to local cache: {e}")
                raw = None

        # If Redis miss / disabled, use local cache
        if raw is None and self._local_cache is not None:
            payload = self._local_cache
        elif raw is None:
            return None
        else:
            try:
                payload = json.loads(raw)
            except Exception:
                return None

        ts = payload.get("ts")
        data = payload.get("data", [])
        if ts is None:
            return None

        age = time.time() - float(ts)
        if age > max_age_seconds:
            return None

        try:
            return [StockPrice(**item) for item in data]
        except Exception as e:
            print(f"[cache] Failed to hydrate StockPrice objects from cache: {e}")
            return None
