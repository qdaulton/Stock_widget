import asyncio
from typing import List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request

from models import StockPrice, PriceUpdateMessage, AlertRule, AlertEvent
from stocks_service import StockPriceProvider
from cache_service import PriceCache
from alert_service import AlertManager
from webex_service import WebexNotifier

app = FastAPI(title="SmartStock Monitor Backend")

# Allow the frontend (served by nginx or file://) to talk to the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------- logging middleware (handy for demo) --------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f">>> {request.method} {request.url.path}")
    response = await call_next(request)
    print(f"<<< {request.method} {request.url.path} -> {response.status_code}")
    return response


# -------- global services --------

price_provider = StockPriceProvider()
price_cache = PriceCache()

# demo rules; tweak thresholds as you like
alert_rules = {
    1: AlertRule(id=1, symbol="AAPL", operator=">", threshold=200, description="AAPL > 200 (notify WebEx)"),
    2: AlertRule(id=2, symbol="TSLA", operator=">", threshold=180, description="TSLA > 180 (notify WebEx)"),
    3: AlertRule(id=3, symbol="NVDA", operator=">", threshold=1000, description="NVDA > 1000 (high priority)"),
}
alert_manager = AlertManager(alert_rules)

webex_notifier = WebexNotifier.from_env()


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.add(websocket)
        print(f"[ws] client connected, total={len(self.active)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)
            print(f"[ws] client disconnected, total={len(self.active)}")

    async def broadcast_json(self, payload):
        disconnected: List[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


# -------- simple REST endpoints --------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/prices", response_model=List[StockPrice])
async def get_prices_once():
    """
    REST endpoint mainly for debugging; the UI uses WebSockets instead.
    """
    cached = price_cache.get_snapshot()
    if cached:
        return cached

    prices = price_provider.get_prices()
    price_cache.set_snapshot(prices)
    return prices


@app.get("/alerts/rules", response_model=List[AlertRule])
async def get_alert_rules():
    return alert_manager.rules


@app.post("/alerts/rules", response_model=AlertRule)
async def add_alert_rule(rule: AlertRule = Body(...)):
    alert_manager.add_rule(rule)
    return rule


@app.get("/alerts/events", response_model=List[AlertEvent])
async def get_recent_events():
    return alert_manager.recent_events()


# -------- websocket helpers --------
async def _compute_and_broadcast_prices():
    """
    Helper used by the websocket loop: get latest prices (cache + provider),
    update cache, run alert engine, send everything to clients.
    """
    prices = price_cache.get_snapshot()
    if prices is None:
        prices = price_provider.get_prices()
        price_cache.set_snapshot(prices)

    # send price update (ensure datetimes are JSON-serializable)
    msg = PriceUpdateMessage(data=prices)
    await manager.broadcast_json(msg.model_dump(mode="json"))

    # evaluate alerts
    events = alert_manager.evaluate(prices)
    for event in events:
        # send to WebEx (if configured)
        webex_notifier.send_alert(event)
        # broadcast alert to clients
        await manager.broadcast_json({
            "type": "alert",
            "rule_id": event.rule_id,
            "symbol": event.symbol,
            "price": event.price,
            "triggered_at": event.triggered_at.isoformat(),
            "message": event.message,
        })


@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    await manager.connect(websocket)

    # On connect, send cached snapshot immediately if available
    cached = price_cache.get_snapshot()
    if cached:
        snapshot_msg = PriceUpdateMessage(data=cached)
        # IMPORTANT: mode="json" so datetime -> ISO string
        await websocket.send_json(snapshot_msg.model_dump(mode="json"))

    try:
        # Simple loop: every 10 seconds update prices and alerts
        while True:
            await _compute_and_broadcast_prices()
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[ws] Unexpected error in websocket_prices: {e}")
        manager.disconnect(websocket)
