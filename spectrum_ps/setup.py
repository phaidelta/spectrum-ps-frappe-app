import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from spectrum_ps.permissions import setup_roles_and_permissions

RAVEN_WORKSPACE_NAME = "Customer communications"
SALES_ORDER_SERIES = "TKT-.YYYY.MM.-.###"


def after_install():
	run_setup()


def after_migrate():
	run_setup()


def run_setup():
	setup_roles_and_permissions()
	setup_raven_workspace()


def setup_raven_workspace():
	"""Create the workspace that holds all ticket channels."""
	if not frappe.db.exists("DocType", "Raven Workspace"):
		return  # Raven not installed yet; the next migrate will retry

	if frappe.db.exists("Raven Workspace", {"workspace_name": RAVEN_WORKSPACE_NAME}):
		return

	frappe.get_doc(
		{
			"doctype": "Raven Workspace",
			"workspace_name": RAVEN_WORKSPACE_NAME,
			"type": "Public",  # ticket channels themselves stay Private
			"description": "Customer ticket chats",
		}
	).insert(ignore_permissions=True)


def setup_sales_order_naming():
	"""Make Sales Order use our naming series by default."""
	for prop in ("options", "default"):
		make_property_setter("Sales Order", "naming_series", prop, SALES_ORDER_SERIES, "Text")
	frappe.clear_cache(doctype="Sales Order")
