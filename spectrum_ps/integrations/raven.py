import requests
import frappe

from .config import require_setting


class RavenClient:
	"""Client for communicating with Raven using a bot account."""

	def __init__(self):
		self.base_url = require_setting(
			"raven_base_url"
		).rstrip("/")

		self.api_key = require_setting(
			"raven_api_key"
		)

		self.api_secret = require_setting(
			"raven_api_secret"
		)

	def _headers(self):
		return {
			"Authorization": (
				f"token {self.api_key}:{self.api_secret}"
			),
			"Content-Type": "application/json",
			"Accept": "application/json",
		}

	# ---------------------------------------------------------
	# Send message to Raven
	# ---------------------------------------------------------

	def send_message(
		self,
		text: str,
		channel: str,
	):
		if not channel:
			frappe.throw(
				"Raven channel ID is required"
			)

		if not text:
			frappe.throw(
				"Raven message text is required"
			)

		url = (
			f"{self.base_url}"
			"/api/method/raven.api.raven_message.send_message"
		)

		payload = {
			"channel_id": channel,
			"text": text,
		}

		try:
			response = requests.post(
				url,
				headers=self._headers(),
				json=payload,
				timeout=15,
			)

			if response.status_code >= 400:
				frappe.log_error(
					title="Raven API Error",
					message=(
						f"Status: {response.status_code}\n"
						f"URL: {url}\n"
						f"Response: {response.text}"
					),
				)

			response.raise_for_status()

			try:
				return response.json()

			except ValueError:
				return {
					"status_code": response.status_code,
					"text": response.text,
				}

		except requests.RequestException:
			frappe.log_error(
				title="Raven API Request Failed",
				message=frappe.get_traceback(),
			)
			raise

	# ---------------------------------------------------------
	# Get Raven messages
	# ---------------------------------------------------------

	def get_messages(
		self,
		channel: str,
	):
		"""
		Get messages from a Raven channel.
		"""

		if not channel:
			frappe.throw(
				"Raven channel ID is required"
			)

		url = (
			f"{self.base_url}"
			"/api/method/raven.api.chat_stream.get_messages"
		)

		params = {
			"channel_id": channel,
		}

		try:
			response = requests.get(
				url,
				headers=self._headers(),
				params=params,
				timeout=15,
			)

			if response.status_code >= 400:
				frappe.log_error(
					title="Raven Get Messages Failed",
					message=(
						f"Status: {response.status_code}\n"
						f"URL: {response.url}\n"
						f"Response: {response.text}"
					),
				)

			response.raise_for_status()

			return response.json()

		except requests.RequestException:
			frappe.log_error(
				title="Raven Get Messages Request Failed",
				message=frappe.get_traceback(),
			)
			raise
