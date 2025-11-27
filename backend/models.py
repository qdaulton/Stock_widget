from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class StockPrice(BaseModel):
    symbol: str
    price: float
    change: float
    percentChange: float
    ts: datetime


class PriceUpdateMessage(BaseModel):
    type: str = "price_update"
    data: List[StockPrice]


class AlertRule(BaseModel):
    """
    A single alert rule such as "AAPL > 200".
    """
    id: int
    symbol: str
    operator: str  # ">" or "<"
    threshold: float
    description: str
    enabled: bool = True
    cooldown_seconds: int = 60
    last_triggered: Optional[datetime] = None


class AlertEvent(BaseModel):
    """
    A concrete alert firing at a specific time.
    """
    rule_id: int
    symbol: str
    price: float
    triggered_at: datetime
    message: str
