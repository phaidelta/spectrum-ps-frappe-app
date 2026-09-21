from urllib.parse import urlsplit

import frappe
from frappe.exceptions import ValidationError
from frappe.utils.oauth import get_oauth2_authorize_url


ALLOWED_PROVIDERS = frozenset({"google", "facebook"})


def _get_redirect_url() -> str:
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
    redirect_url = _get_redirect_url()
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
