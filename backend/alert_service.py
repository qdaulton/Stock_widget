from datetime import datetime, timezone, timedelta
from typing import Dict, List

from models import AlertRule, AlertEvent, StockPrice


class AlertManager:
    """
    In-memory alert rule engine.

    - Stores alert rules.
    - On each price snapshot, evaluates rules.
    - Applies cooldown to avoid spamming.
    - Keeps a small history of recent events.
    """

    def __init__(self, rules: Dict[int, AlertRule]):
        self._rules: Dict[int, AlertRule] = dict(rules)
        self._events: List[AlertEvent] = []

    # --------------- rule management ---------------

    @property
    def rules(self) -> List[AlertRule]:
        return list(self._rules.values())

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.id] = rule

    def clear_rules(self) -> None:
        self._rules.clear()

    # --------------- evaluation helpers ---------------

    def _condition_met(self, rule: AlertRule, price: float) -> bool:
        op = rule.operator.strip()
        if op == ">":
            return price > rule.threshold
        if op == "<":
            return price < rule.threshold
        return False  # unknown operator

    def _can_trigger(self, rule: AlertRule, now: datetime) -> bool:
        if rule.last_triggered is None:
            return True
        delta = now - rule.last_triggered
        return delta >= timedelta(seconds=rule.cooldown_seconds)

    def evaluate(self, prices: List[StockPrice]) -> List[AlertEvent]:
        """
        Evaluate all rules against a price snapshot and return the
        list of newly-fired alert events.
        """
        if not prices:
            return []

        now = datetime.now(timezone.utc)
        events: List[AlertEvent] = []

        price_by_symbol = {p.symbol.upper(): p for p in prices}

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            p = price_by_symbol.get(rule.symbol.upper())
            if p is None:
                continue

            current_price = p.price
            if not self._condition_met(rule, current_price):
                continue

            if not self._can_trigger(rule, now):
                continue

            msg = f"{rule.symbol} {rule.operator} {rule.threshold} (now {current_price:.2f})"

            rule.last_triggered = now

            event = AlertEvent(
                rule_id=rule.id,
                symbol=rule.symbol,
                price=current_price,
                triggered_at=now,
                message=msg,
            )
            events.append(event)
            self._events.append(event)

        # keep last 50 events
        if len(self._events) > 50:
            self._events = self._events[-50:]

        return events

    def recent_events(self) -> List[AlertEvent]:
        return list(self._events)
