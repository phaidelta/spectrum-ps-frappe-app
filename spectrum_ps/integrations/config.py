import frappe


def setting(name: str, default=None):
    """Read a site config value or environment variable."""
    value = frappe.conf.get(name)
    if value is None:
        value = frappe.get_env(name)
    return value if value is not None else default


def require_setting(name: str) -> str:
    value = setting(name)
    if not value:
        frappe.throw(f"Missing required setting: {name}")
    return str(value)
