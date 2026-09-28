import json
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import frappe
from frappe import _
from frappe.exceptions import ValidationError
from frappe.utils import get_url
from frappe.utils.oauth import (
	SignupDisabledError,
	get_email,
	get_oauth2_authorize_url,
	get_user_record,
	update_oauth_user,
)
from frappe.utils.response import Response

from .integrations.config import require_setting
from .integrations.raven import RavenClient
from .integrations.twilio import validate_webhook_signature
from .realtime import publish_message


if TYPE_CHECKING:
	from frappe.core.doctype.user.user import User


# ---------------------------------------------------------------------------
# Raven channel
# ---------------------------------------------------------------------------

def get_raven_channel_and_sales_order(sender_phone: str):
	"""
	Return the fixed Raven channel used by the WhatsApp PoC.

	For this PoC we intentionally do NOT:
	- search Sales Orders
	- search customer records
	- listen to Raven events

	Every incoming WhatsApp message goes to the configured Raven channel.
	"""

	channel_id = require_setting("raven_channel_id")

	if not channel_id:
		frappe.throw(_("Raven channel ID is not configured"))

	return channel_id, None


# ---------------------------------------------------------------------------
# Social login
# ---------------------------------------------------------------------------

def _get_social_redirect_url() -> str:
	redirect_url = frappe.conf.get("social_login_redirect_url")

	if not isinstance(redirect_url, str) or not redirect_url.strip():
		frappe.throw("Social login redirect URL is not configured")

	redirect_url = redirect_url.strip()
	parsed = urlsplit(redirect_url)

	if (
		parsed.scheme not in {"http", "https"}
		or not parsed.netloc
		or parsed.username
		or parsed.password
		or parsed.fragment
	):
		frappe.throw("Invalid social login redirect URL")

	return redirect_url


def _is_missing_client_secret(
	error: ValidationError,
	provider: str,
) -> bool:
	return str(error) == (
		f"Password not found for Social Login Key {provider} client_secret"
	)


@frappe.whitelist(allow_guest=True)
def get_social_login_urls() -> dict[str, str]:
	redirect_url = _get_social_redirect_url()
	social_login_urls: dict[str, str] = {}

	for provider in sorted(ALLOWED_PROVIDERS):
		try:
			social_login_urls[provider] = get_oauth2_authorize_url(
				provider,
				redirect_url,
			)
		except ValidationError as error:
			if _is_missing_client_secret(error, provider):
				frappe.logger().warning(
					"Skipping social login provider '%s': "
					"client secret is not configured",
					provider,
				)
				continue

			raise

	return social_login_urls


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------

def get_login_with_email_link_ratelimit() -> int:
	return frappe.get_system_settings(
		"rate_limit_email_link_login"
	) or 5


def _generate_temporary_login_link(
	email: str,
	expiry: int,
):
	assert isinstance(email, str)

	key = frappe.generate_hash()

	frappe.cache.set_value(
		f"one_time_login_key:{key}",
		email,
		expires_in_sec=expiry * 60,
	)

	return get_url(
		f"/api/method/spectrum_ps.api.login_via_key?key={key}",
		allow_header_override=False,
	)


# ---------------------------------------------------------------------------
# Customer enquiry
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True, methods=["POST"])
def contact_us(
	user_name,
	email_id,
	phone_no,
	message,
):
	"""Allow guest users to raise an enquiry."""

	doc = frappe.get_doc(
		{
			"doctype": "Customer Inquiry",
			"user_name": user_name,
			"email_id": email_id,
			"phone_no": phone_no,
			"message": message,
		}
	)

	doc.insert(ignore_permissions=True)

	return {
		"status": "success",
		"name": doc.name,
	}


# ---------------------------------------------------------------------------
# Login via key
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True, methods=["GET"])
def login_via_key(key: str):
	"""
	Accept a previously generated login key and login the user.
	"""

	cache_key = f"one_time_login_key:{key}"
	email = frappe.cache.get_value(cache_key)

	if email:
		data = {
			"email": email,
			"first_name": email,
			"last_name": "",
			"sub": email,
		}

		frappe.log(
			f"Logging in with `{email}`"
		)

		return login_website_user(data)

	frappe.respond_as_web_page(
		_("Not Permitted"),
		_("The link you trying to login is invalid or expired."),
		http_status_code=403,
		indicator_color="red",
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def send_customer_email_login_link(email: str):
	try:
		expiry = (
			frappe.get_system_settings(
				"login_with_email_link_expiry"
			)
			or 10
		)

		link = _generate_temporary_login_link(
			email,
			expiry,
		)

		app_name = (
			frappe.get_website_settings("app_name")
			or frappe.get_system_settings("app_name")
			or _("Frappe")
		)

		subject = _("Login To {0}").format(app_name)

		frappe.log(
			f"Sending mail to {email} "
			f"with subject {subject}"
		)

		mail_queue = frappe.sendmail(
			subject=subject,
			recipients=email,
			template="login_with_email_link",
			args={
				"link": link,
				"minutes": expiry,
				"app_name": app_name,
			},
			with_container=True,
			now=True,
		)

		frappe.log(
			f"Mail to {email} in queue "
			f"with queue id {mail_queue.name}"
		)

		return {
			"status": "ok",
			"email_queue": mail_queue.name,
		}

	except frappe.DoesNotExistError:
		frappe.clear_messages()

	except frappe.OutgoingEmailError:
		frappe.clear_messages()

		frappe.log_error(
			title="Login link email could not be sent",
			message=frappe.get_traceback(),
		)

	except Exception:
		frappe.clear_messages()

		frappe.log_error(
			title="Login link generation failed unexpectedly",
			message=frappe.get_traceback(),
		)

	frappe.throw(
		f"Failed to send email to address {email}"
	)


# ---------------------------------------------------------------------------
# Website user login
# ---------------------------------------------------------------------------

def login_website_user(
	data: dict | str,
	*,
	provider: str | None = None,
):
	"""
	Utility method to get/create a website user using an email address
	and log them in without credentials.
	"""

	if isinstance(data, str):
		data = json.loads(data)

	user = get_email(data).lower()

	if not user:
		frappe.respond_as_web_page(
			_("Invalid Request"),
			_("Please ensure that your profile has an email address"),
		)
		return

	try:
		if update_oauth_user(
			user,
			data,
			provider,
		) is False:
			return

	except SignupDisabledError:
		return frappe.respond_as_web_page(
			"Signup is Disabled",
			"Sorry. Signup from Website is disabled.",
			success=False,
			http_status_code=403,
		)

	frappe.db.commit()

	this_user: User = get_user_record(
		user,
		data,
		provider,
	)

	if this_user.user_type != "Website User":
		return frappe.respond_as_web_page(
			_("Not Permitted"),
			_(
				"You are trying to log in using an administrator account. "
				"This portal is restricted to website users only. "
				"Please use the Administrator portal to log in instead."
			),
			http_status_code=403,
			indicator_color="red",
			primary_action="/admin-redirect",
			primary_label="Open Admin portal",
		)

	frappe.local.login_manager.login_as(user)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/website-redirect"


# ---------------------------------------------------------------------------
# WhatsApp -> Raven
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def whatsapp_webhook(*args, **kwargs):
	"""
	Receive an inbound WhatsApp message from Twilio
	and send it to the configured Raven channel.

	Flow:

	WhatsApp
	    ↓
	Twilio
	    ↓
	ngrok
	    ↓
	Frappe webhook
	    ↓
	RavenClient
	    ↓
	Raven Bot API
	    ↓
	Fixed Raven Channel
	"""

	# ---------------------------------------------------------------
	# 1. Get Twilio request
	# ---------------------------------------------------------------

	request_url = (
		getattr(
			frappe.request,
			"url",
			"",
		)
		if frappe.request
		else ""
	)

	form = frappe.form_dict or {}

	# ---------------------------------------------------------------
	# 2. Validate Twilio signature
	# ---------------------------------------------------------------

	if request_url and not validate_webhook_signature(
		request_url,
		form,
	):
		frappe.throw(
			_("Invalid Twilio signature"),
			frappe.PermissionError,
		)

	# ---------------------------------------------------------------
	# 3. Extract WhatsApp message
	# ---------------------------------------------------------------

	sender = (
		form.get("From")
		or ""
	).strip()

	profile_name = (
		form.get("ProfileName")
		or sender
	).strip()

	body = (
		form.get("Body")
		or ""
	).strip()

	message_sid = form.get("MessageSid")

	# ---------------------------------------------------------------
	# 4. Validate sender
	# ---------------------------------------------------------------

	if not sender:
		frappe.throw(
			_("Missing WhatsApp sender")
		)

	# ---------------------------------------------------------------
	# 5. Validate message body
	# ---------------------------------------------------------------

	if not body:
		frappe.logger().warning(
			"Received empty WhatsApp message from %s",
			sender,
		)

		return Response(
			'<?xml version="1.0" encoding="UTF-8"?>'
			"<Response></Response>",
			content_type="application/xml",
		)

	# ---------------------------------------------------------------
	# 6. Get fixed Raven channel
	# ---------------------------------------------------------------

	channel_id, _ = get_raven_channel_and_sales_order(
		sender
	)

	# ---------------------------------------------------------------
	# 7. Build Raven message
	# ---------------------------------------------------------------

	raven_text = (
		f"WhatsApp - {profile_name} "
		f"({sender}): {body}"
	)

	# ---------------------------------------------------------------
	# 8. Send message to Raven
	# ---------------------------------------------------------------

	try:
		raven_response = RavenClient().send_message(
			text=raven_text,
			channel=channel_id,
		)

	except Exception:
		frappe.log_error(
			title="WhatsApp to Raven Failed",
			message=(
				f"Sender: {sender}\n"
				f"Channel: {channel_id}\n"
				f"Message SID: {message_sid}\n\n"
				f"{frappe.get_traceback()}"
			),
		)

		# Return an empty TwiML response instead of exposing
		# internal Raven/Frappe errors to Twilio.
		return Response(
			'<?xml version="1.0" encoding="UTF-8"?>'
			"<Response></Response>",
			content_type="application/xml",
		)

	# ---------------------------------------------------------------
	# 9. Publish local realtime notification
	# ---------------------------------------------------------------

	publish_message(
		"spectrum_ps_whatsapp_message",
		direction="whatsapp_to_raven",
		message={
			"message_sid": message_sid,
			"from": sender,
			"profile_name": profile_name,
			"body": body,
			"channel_id": channel_id,
			"raven": raven_response,
		},
	)

	# ---------------------------------------------------------------
	# 10. Return TwiML to Twilio
	# ---------------------------------------------------------------

	return Response(
		'<?xml version="1.0" encoding="UTF-8"?>'
		"<Response></Response>",
		content_type="application/xml",
	)
