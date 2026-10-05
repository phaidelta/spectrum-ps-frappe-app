from urllib.parse import urljoin

import requests

from .config import require_setting


class RavenClient:
	def __init__(self):
		self.base_url = require_setting("raven_base_url").rstrip("/") + "/"
		self.api_key = require_setting("raven_api_key")
		self.api_secret = require_setting("raven_api_secret")
		self.default_channel_id = require_setting("raven_channel_id") if self._has_default_channel() else None

	def _has_default_channel(self):
		import frappe

		return bool(frappe.conf.get("raven_channel_id") or frappe.get_env("RAVEN_CHANNEL_ID"))

	@property
	def headers(self):
		return {
			"Authorization": f"token {self.api_key}:{self.api_secret}",
			"Accept": "application/json",
			"Content-Type": "application/json",
		}

	def send_message(self, text: str, channel: str | None = None) -> dict:
		channel_id = channel or self.default_channel_id
		if not channel_id:
			raise ValueError("Raven channel is required")
		response = requests.post(
			urljoin(self.base_url, "api/method/raven.api.raven_message.send_message"),
			headers=self.headers,
			json={"channel_id": channel_id, "text": text},
			timeout=15,
		)
		response.raise_for_status()
		return response.json()

	def get_messages(self, channel: str | None = None) -> list[dict]:
		channel_id = channel or self.default_channel_id
		if not channel_id:
			raise ValueError("Raven channel is required")
		response = requests.get(
			urljoin(self.base_url, "api/method/raven.api.chat_stream.get_messages"),
			headers=self.headers,
			params={"channel_id": channel_id},
			timeout=15,
		)
		response.raise_for_status()
		payload = response.json()
		messages = payload.get("message", [])
		if isinstance(messages, dict):
			messages = messages.get("messages") or messages.get("data") or []
		return messages if isinstance(messages, list) else []
