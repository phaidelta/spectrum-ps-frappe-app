from urllib.parse import urljoin

import requests

from .config import require_setting


class RavenClient:
    def __init__(self):
        self.base_url = require_setting("raven_base_url").rstrip("/") + "/"
        self.api_key = require_setting("raven_api_key")
        self.api_secret = require_setting("raven_api_secret")
        self.channel_id = require_setting("raven_channel_id")

    @property
    def headers(self):
        return {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def send_message(self, text: str, channel: str | None = None) -> dict:
        response = requests.post(
            urljoin(self.base_url, "api/method/raven.api.raven_message.send_message"),
            headers=self.headers,
            json={"channel_id": self.channel_id, "text": text},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_messages(self) -> list[dict]:
        response = requests.get(
            urljoin(self.base_url, "api/method/raven.api.chat_stream.get_messages"),
            headers=self.headers,
            params={"channel_id": self.channel_id},
            timeout=15,
        )
        response.raise_for_status()

        payload = response.json()
        messages = payload.get("message", [])
        if isinstance(messages, dict):
            messages = messages.get("messages") or messages.get("data") or []
        return messages if isinstance(messages, list) else []
