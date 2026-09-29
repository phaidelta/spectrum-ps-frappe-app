import json
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
import requests
import frappe
from frappe import _
from frappe.exceptions import ValidationError
from frappe.rate_limiter import rate_limit
from frappe.utils import get_url
from frappe.utils.oauth import (
	SignupDisabledError,
	get_email,
	get_oauth2_authorize_url,
	get_user_record,
	update_oauth_user,
)
from frappe.utils.response import Response

from .integrations.raven import RavenClient
from .integrations.twilio import validate_webhook_signature
from .messaging import get_active_sales_order_for_customer, get_customer_by_whatsapp
from .realtime import publish_message

if TYPE_CHECKING:
	from frappe.core.doctype.user.user import User


def get_raven_channel_and_sales_order(sender_phone: str):
	"""Resolve WhatsApp sender -> Customer -> active Sales Order -> Raven Channel."""
	customer = get_customer_by_whatsapp(sender_phone)
	so = get_active_sales_order_for_customer(customer.name)
	if not so:
		frappe.throw(
			_("Customer {0} has no active In Progress Sales Order.").format(customer.name)
		)

	channel_id = so.custom_raven_channel
	if not channel_id:
		frappe.throw(
			_("Sales Order {0} has no Raven Channel.").format(so.name)
		)

	return channel_id, so.name, customer


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


def _is_missing_client_secret(error: ValidationError, provider: str) -> bool:
	return str(error) == (f"Password not found for Social Login Key {provider} client_secret")


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
					"Skipping social login provider '%s': client secret is not configured",
					provider,
				)
				continue

			raise

	return social_login_urls


def get_login_with_email_link_ratelimit() -> int:
	return frappe.get_system_settings("rate_limit_email_link_login") or 5


def _generate_temporary_login_link(email: str, expiry: int):
	assert isinstance(email, str)

	key = frappe.generate_hash()
	frappe.cache.set_value(f"one_time_login_key:{key}", email, expires_in_sec=expiry * 60)

	return get_url(
		f"/api/method/spectrum_ps.api.login_via_key?key={key}",
		allow_header_override=False,
	)

@frappe.whitelist(allow_guest=True, methods=["POST"])
def contact_us(user_name, email_id, phone_no, message):
	"""Allows Guest users to to raise enquiry"""
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
	return {"status": "success", "name": doc.name}

@frappe.whitelist(allow_guest=True, methods=["GET"])
# @rate_limit(limit=get_login_with_email_link_ratelimit, seconds=60 * 60)
def login_via_key(key: str):
	"""
	Accept a previously generated login key (sent to the user) and login, then
	redirect to the home page
	"""

	cache_key = f"one_time_login_key:{key}"
	email = frappe.cache.get_value(cache_key)

	# TODO: Implement phone number authentication

	if email:
		# TODO: Should this be removed? This immediately invalidates the key, so it becomes one-time use.
		# Instead, just directly redirect to the home page
		# frappe.cache.delete_value(cache_key)

		# TODO: Defaults change?
		data = {
			"email": email,
			"first_name": email,
			"last_name": "",
			"sub": email,  # user_id_property
		}

		# Allow to be logged in as this user
		frappe.log(f"Logging in with `{email}`")
		return login_website_user(data)

	frappe.respond_as_web_page(
		_("Not Permitted"),
		_("The link you trying to login is invalid or expired."),
		http_status_code=403,
		indicator_color="red",
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
# @rate_limit(limit=get_login_with_email_link_ratelimit, seconds=60 * 60)
def send_customer_email_login_link(email: str):
	try:
		expiry = frappe.get_system_settings("login_with_email_link_expiry") or 10
		link = _generate_temporary_login_link(email, expiry)

		app_name = (
			frappe.get_website_settings("app_name") or frappe.get_system_settings("app_name") or _("Frappe")
		)

		subject = _("Login To {0}").format(app_name)
		frappe.log(f"Sending mail to {email} with subject {subject}")

		# Send E-mail to the given address
		mail_queue = frappe.sendmail(
			subject=subject,
			recipients=email,
			template="login_with_email_link",
			args={"link": link, "minutes": expiry, "app_name": app_name},
			with_container=True,
			# TODO: This param is new in v16.35
			# wrapper="templates/emails/auth_email.html",
			now=True,
		)
		frappe.log(f"Mail to {email} in queue with queue id {mail_queue.name}")

		return {"status": "ok", "email_queue": mail_queue.name}

	except frappe.DoesNotExistError:
		frappe.clear_messages()
	except frappe.OutgoingEmailError:
		frappe.clear_messages()
		frappe.log_error(title="Login link email could not be sent", message=frappe.get_traceback())
	except Exception:
		frappe.clear_messages()
		frappe.log_error(
			title="Login link generation failed unexpectedly",
			message=frappe.get_traceback(),
		)

	frappe.throw(f"Failed to send email to address {email}")


def login_website_user(
	data: dict | str,
	*,
	provider: str | None = None,
):
	"""
	Utility method to get / create a new website user using email address, and log-in with it (no credentials)
	"""

	if isinstance(data, str):
		data = json.loads(data)

	# All user emails are stored as lowercase, but OAuth provider could have it in mixed case.
	# We pass the email as-is to LoginManager, which could result in a session with an incorrect email.
	user = get_email(data).lower()

	if not user:
		frappe.respond_as_web_page(
			_("Invalid Request"),
			_("Please ensure that your profile has an email address"),
		)
		return

	try:
		if update_oauth_user(user, data, provider) is False:
			return

	except SignupDisabledError:
		return frappe.respond_as_web_page(
			"Signup is Disabled",
			"Sorry. Signup from Website is disabled.",
			success=False,
			http_status_code=403,
		)

	frappe.db.commit()

	# Only allow Website users. Show error (and admin redirect link) page
	# NOTE: this is re-fetched as `update_oauth_user` does not return the new user instance.
	this_user: User = get_user_record(user, data, provider)
	print("User:", this_user)
	print(f"This user: {this_user}, type: {this_user.user_type}")
	frappe.log(f"This user: {this_user}, type: {this_user.user_type}")

	if this_user.user_type != "Website User":
		# Show error as user is overprivileged, and ask to use admin portal instead
		return frappe.respond_as_web_page(
			_("Not Permitted"),
			_(
				"You are trying to log in using an administrator account. This portal is restricted to website users only. Please use the Administrator portal to log in instead."
			),
			http_status_code=403,
			indicator_color="red",
			primary_action="/admin-redirect",
			primary_label="Open Admin portal",
		)

	# Success path
	frappe.local.login_manager.login_as(user)
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/website-redirect"

	# Fallback to the channel ID defined in your config (e.g., tkt-001 channel)
	default_channel = require_setting("raven_channel_id")
	return default_channel, None


@frappe.whitelist(allow_guest=True)
def whatsapp_webhook(*args, **kwargs):
	"""Receive Twilio WhatsApp messages and route them to the customer's Raven channel."""
	request_url = getattr(frappe.request, "url", "") if frappe.request else ""
	form = frappe.form_dict or {}

	if request_url and not validate_webhook_signature(request_url, form):
		frappe.throw(_("Invalid Twilio signature"), frappe.PermissionError)

	sender = (form.get("From") or "").strip()
	profile_name = (form.get("ProfileName") or sender).strip()
	body = (form.get("Body") or "").strip()
	message_sid = form.get("MessageSid")

	if not sender:
		frappe.throw(_("Missing WhatsApp sender"))

	if not body:
		return Response(
			'<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
			content_type="application/xml",
		)

	channel_id, so_name, customer = get_raven_channel_and_sales_order(sender)
	raven_text = f"WhatsApp - {profile_name} ({sender}): {body}"

	raven_response = RavenClient().send_message(
		text=raven_text,
		channel=channel_id,
	)

	publish_message(
		"spectrum_ps_whatsapp_message",
		direction="whatsapp_to_raven",
		message={
			"message_sid": message_sid,
			"from": sender,
			"customer": customer.name,
			"sales_order": so_name,
			"body": body,
			"channel_id": channel_id,
			"raven": raven_response,
		},
	)

	return Response(
		'<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
		content_type="application/xml",
	)


import frappe
import requests

@frappe.whitelist()
def send_outbound_whatsapp(doc, method=None):
    """Triggered automatically when a new Raven Message is created."""
    print(f"\n================ [OUTBOUND HOOK TRIGGERED] ================")
    print(f"Message ID: {doc.name}")

    # Prevent loops from inbound webhook
    if getattr(doc, "via_whatsapp", False) or getattr(frappe.flags, "in_whatsapp_webhook", False):
        print("Skipped: Triggered by inbound WhatsApp webhook flag.")
        return

    # Extract Channel ID
    channel_id = getattr(doc, "channel_id", None) or getattr(doc, "parent", None)
    print(f"Channel ID resolved: {channel_id}")

    if not channel_id:
        print("Aborted: No channel ID found on doc.")
        return

    # Fetch Channel Document
    try:
        channel = frappe.get_doc("Raven Channel", channel_id)
    except Exception as e:
        print(f"Aborted: Could not fetch Raven Channel {channel_id} -> {e}")
        return

    # 1. Direct phone fields on Raven Channel
    recipient_phone = (
        getattr(channel, "mobile_no", None)
        or getattr(channel, "phone", None)
        or getattr(channel, "custom_mobile_no", None)
    )

    # 2. Extract phone via Sales Order derived from channel_name or linked_document
    if not recipient_phone:
        sales_order_name = getattr(channel, "linked_document", None)

        # If linked_document is None, parse channel_name (e.g., 'sal-ord-2026-00007' -> 'SAL-ORD-2026-00007')
        if not sales_order_name and getattr(channel, "channel_name", None):
            sales_order_name = channel.channel_name.upper()

        if sales_order_name and frappe.db.exists("Sales Order", sales_order_name):
            so_doc = frappe.get_doc("Sales Order", sales_order_name)
            # Direct phone fields on Sales Order
            recipient_phone = (
                getattr(so_doc, "contact_mobile", None)
                or getattr(so_doc, "mobile_no", None)
                or getattr(so_doc, "phone", None)
            )

            # Fallback to linked Contact or Customer
            if not recipient_phone and getattr(so_doc, "customer", None):
                contact_name = frappe.db.get_value("Dynamic Link", {
                    "link_doctype": "Customer",
                    "link_name": so_doc.customer,
                    "parenttype": "Contact"
                }, "parent")

                if contact_name:
                    contact = frappe.get_doc("Contact", contact_name)
                    recipient_phone = contact.mobile_no or contact.phone

                # Fallback to Customer document mobile
                if not recipient_phone:
                    customer_doc = frappe.get_doc("Customer", so_doc.customer)
                    recipient_phone = getattr(customer_doc, "mobile_no", None) or getattr(customer_doc, "phone", None)

    print(f"Recipient Phone resolved: {recipient_phone}")

    if not recipient_phone:
        print(f"Aborted: No phone number associated with channel {channel_id} or Sales Order.")
        return

    # Sanitize Phone Number (digits only)
    recipient_phone = "".join(filter(str.isdigit, str(recipient_phone)))

    # Fetch API Credentials
    phone_number_id = frappe.conf.get("whatsapp_phone_number_id")
    access_token = frappe.conf.get("whatsapp_access_token")

    if not phone_number_id or not access_token:
        print("Aborted: Missing whatsapp_phone_number_id or whatsapp_access_token in site_config.json")
        return

    # Call Meta API
    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    message_text = doc.text or getattr(doc, "content", "")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text
        }
    }

    print(f"Posting to Meta API: {url} | To: {recipient_phone}")
    response = requests.post(url, json=payload, headers=headers)

    print(f"Meta Response Code: {response.status_code}")
    print(f"Meta Response Data: {response.text}")
    print(f"===========================================================\n")

    if response.status_code != 200:
        frappe.log_error(title="WhatsApp Outbound Failed", message=response.text)
