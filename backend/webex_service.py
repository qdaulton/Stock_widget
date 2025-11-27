import json
import os
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from models import AlertEvent


class WebexNotifier:
    """
    Sends alert messages to a WebEx space using a bot token.

    Requires environment variables:
      - WEBEX_BOT_TOKEN : Bot access token
      - WEBEX_ROOM_ID   : Target roomId to post messages into

    If configuration is missing, the notifier becomes a no-op but
    logs what it *would* have sent.
    """

    def __init__(self, bot_token: Optional[str], room_id: Optional[str]):
        self.bot_token = bot_token
        self.room_id = room_id

        if not self.bot_token or not self.room_id:
            print("[webex] WARNING: WebEx not fully configured; alerts will be logged only.")

    @classmethod
    def from_env(cls) -> "WebexNotifier":
        token = os.getenv("WEBEX_BOT_TOKEN")
        room_id = os.getenv("WEBEX_ROOM_ID")
        return cls(bot_token=token, room_id=room_id)

    # --------------- public API ---------------

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.room_id)

    def send_alert(self, event: AlertEvent) -> None:
        """
        Post a simple message into the configured WebEx room.
        """
        if not self.is_configured():
            print(f"[webex] (dry-run) Would send alert to WebEx: {event.message}")
            return

        url = "https://webexapis.com/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

        text = (
            f"🚨 Stock Alert: {event.symbol}\n"
            f"{event.message}\n"
            f"Triggered at {event.triggered_at.isoformat()}"
        )
        payload = {
            "roomId": self.room_id,
            "text": text,
        }

        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=5) as resp:
                resp.read()
            print(f"[webex] Alert sent to WebEx for rule {event.rule_id} ({event.symbol}).")
        except HTTPError as e:
            print(f"[webex] HTTP error sending alert to WebEx: {e.code} {e.reason}")
        except URLError as e:
            print(f"[webex] Network error sending alert to WebEx: {e.reason}")
        except Exception as e:
            print(f"[webex] Unexpected error sending alert to WebEx: {e}")
