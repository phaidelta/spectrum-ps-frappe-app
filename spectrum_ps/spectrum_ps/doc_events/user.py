import frappe


def check_and_add_role(doc, method):
	target_role = "Raven User"
	spectrum_user_role = "Spectrum PS User"
	technician_role = "Technician"

	user_roles = [r.role for r in doc.roles]
	if spectrum_user_role in user_roles and target_role not in user_roles:
		doc.add_roles(target_role)
		frappe.msgprint(
			f"Role '{target_role}' was added automatically because '{spectrum_user_role}' is present.",
			alert=True,
		)

	if technician_role in user_roles and not frappe.db.exists("Technician", {"user": doc.name}):
		frappe.get_doc(
			{
				"doctype": "Technician",
				"user": doc.name,
				"technician_name": doc.full_name or doc.name,
			}
		).insert(ignore_permissions=True)
