import frappe


def check_and_add_role(doc, method):
	target_role = "Raven User"
	spectrum_user_role = "Spectrum PS User"

	user_roles = [r.role for r in doc.roles]
	if spectrum_user_role in user_roles and target_role not in user_roles:
		doc.add_roles("Raven User")
		frappe.msgpring(
			f"Role '{target_role}' was added automatically because '{spectrum_user_role}' is present.",
			alert=True,
		)

	# TODO: Check if "Technician" role is added and add a `Technician` doc linked to this doc (similar to how it's done for Raven User). No removing. Create Technician with other fields default values
