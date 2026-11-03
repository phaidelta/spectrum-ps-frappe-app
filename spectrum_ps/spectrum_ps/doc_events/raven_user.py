import frappe

from spectrum_ps.setup import RAVEN_WORKSPACE_NAME  # "Customer communications"


def add_to_workspace(doc, method=None):
	"""Raven User created: add it to the Customer communications workspace. Never raises."""
	try:
		# Bots (such as a customer's WhatsApp bot) are not workspace members
		if doc.get("type") == "Bot":
			return

		# Only enabled System Users, as agreed
		if doc.get("user"):
			user_type, enabled = frappe.db.get_value("User", doc.user, ["user_type", "enabled"])
			if user_type != "System User" or not enabled:
				return

		if not frappe.db.exists("Raven Workspace", RAVEN_WORKSPACE_NAME):
			frappe.log(f"Workspace `{RAVEN_WORKSPACE_NAME}` not found; `{doc.name}` not added")

			return

		if frappe.db.exists("Raven Workspace Member", {"workspace": RAVEN_WORKSPACE_NAME, "user": doc.name}):
			return  # already a member

		frappe.get_doc(
			{
				"doctype": "Raven Workspace Member",
				"workspace": RAVEN_WORKSPACE_NAME,
				"user": doc.name,
				"is_admin": 0,
			}
		).insert(ignore_permissions=True)
		frappe.log(f"Added Raven User `{doc.name}` to workspace `{RAVEN_WORKSPACE_NAME}`")
	except Exception:
		frappe.log_error(
			title="Raven workspace: could not add Raven User",
			message=f"Raven User: {doc.name}\n{frappe.get_traceback()}",
		)


def remove_from_workspace(doc, method=None):
	"""Raven User deleted: remove its membership from the Customer communications workspace."""
	try:
		members = frappe.get_all(
			"Raven Workspace Member",
			filters={"workspace": RAVEN_WORKSPACE_NAME, "user": doc.name},
			pluck="name",
		)
		for member in members:
			# delete_doc (not a raw SQL delete) so Raven's own hooks on the member still run
			frappe.delete_doc("Raven Workspace Member", member, ignore_permissions=True)
			frappe.log(f"Removed Raven User `{doc.name}` from workspace `{RAVEN_WORKSPACE_NAME}`")
	except Exception:
		frappe.log_error(
			title="Raven workspace: could not remove Raven User",
			message=f"Raven User: {doc.name}\n{frappe.get_traceback()}",
		)
