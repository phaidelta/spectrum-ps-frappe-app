import json
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

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

if TYPE_CHECKING:
    from frappe.core.doctype.user.user import User


ALLOWED_PROVIDERS = frozenset({"google", "facebook"})


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
    frappe.cache.set_value(
        f"one_time_login_key:{key}", email, expires_in_sec=expiry * 60
    )

    return get_url(
        f"/api/method/spectrum_ps.api.login_via_key?key={key}",
        allow_header_override=False,
    )


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
            frappe.get_website_settings("app_name")
            or frappe.get_system_settings("app_name")
            or _("Frappe")
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
        frappe.log_error(
            title="Login link email could not be sent", message=frappe.get_traceback()
        )
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
