import json
import os
import random
from datetime import datetime, timezone
from typing import List
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from models import StockPrice

DEFAULT_SYMBOLS = ["AAPL", "TSLA", "NVDA", "MSFT"]

# Global switch for mock mode.
# Set this to True if you want the backend to use ONLY mock data
# (no Finnhub calls).
USE_MOCK_PRICES = False  # you can toggle this for demos


class StockPriceProvider:
    """
    Fetches current prices for a list of stock symbols.

    - In "real" mode, uses Finnhub's /quote endpoint.
    - On any error, falls back to deterministic mock prices
      so that the UI always has something to show.
    """

    def __init__(self, symbols: List[str] | None = None):
        self.symbols = symbols or DEFAULT_SYMBOLS
        self.api_key = os.getenv("FINNHUB_TOKEN")
        if not self.api_key:
            print("[stocks_service] FINNHUB_TOKEN not set; falling back to mock prices only.")
            global USE_MOCK_PRICES
            USE_MOCK_PRICES = True

    # --------------- Finnhub helpers ---------------

    def _finnhub_url(self, symbol: str) -> str:
        return f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={self.api_key}"

    def _fetch_symbol_from_finnhub(self, symbol: str, now: datetime) -> StockPrice:
        if not self.api_key:
            raise RuntimeError("FINNHUB_TOKEN not configured")

        url = self._finnhub_url(symbol)
        with urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        # Finnhub /quote fields:
        # c: current price
        # pc: previous close
        current = float(payload.get("c") or 0.0)
        prev_close = float(payload.get("pc") or current)

        change = current - prev_close
        percent = (change / prev_close * 100) if prev_close else 0.0

        return StockPrice(
            symbol=symbol.upper(),
            price=current,
            change=change,
            percentChange=percent,
            ts=now,
        )

    # --------------- mock helpers ---------------

    def _mock_price_value(self, symbol: str) -> float:
        base = {
            "AAPL": 190,
            "TSLA": 180,
            "NVDA": 1100,
            "MSFT": 420,
        }.get(symbol.upper(), 100)

        jitter = random.uniform(-3, 3)
        return max(base + jitter, 1)

    def _fallback_price(self, symbol: str, now: datetime) -> StockPrice:
        price = self._mock_price_value(symbol)
        change = random.uniform(-2, 2)
        percent = (change / price * 100) if price else 0.0

        return StockPrice(
            symbol=symbol.upper(),
            price=round(price, 2),
            change=round(change, 2),
            percentChange=round(percent, 2),
            ts=now,
        )

    def _fallback_snapshot(self, now: datetime) -> List[StockPrice]:
        return [self._fallback_price(sym, now) for sym in self.symbols]

    # --------------- public API ---------------

    def get_prices(self) -> List[StockPrice]:
        now = datetime.now(timezone.utc)

        # FULL MOCK MODE: no external API at all
        if USE_MOCK_PRICES:
            return self._fallback_snapshot(now)

        prices: List[StockPrice] = []

        for sym in self.symbols:
            try:
                prices.append(self._fetch_symbol_from_finnhub(sym, now))
            except (HTTPError, URLError, RuntimeError, ValueError, Exception) as e:
                print(f"[stocks_service] Finnhub failed for {sym}, fallback used: {e}")
                prices.append(self._fallback_price(sym, now))

        return prices
