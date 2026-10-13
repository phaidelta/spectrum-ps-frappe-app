import frappe

def add_custom_permission(doctype, role,**kwargs):

	perm = frappe.db.get_value(
        "Custom DocPerm", {
            "parent": doctype,
            "role": role,
        },
        "name")
	permission_data = {
        "select": kwargs.get("select", 0),
        "read": kwargs.get("read", 0),
        "write": kwargs.get("write", 0),
        "create": kwargs.get("create", 0),
        "delete": kwargs.get("delete", 0),
        "submit": kwargs.get("submit", 0),
        "cancel": kwargs.get("cancel", 0),
        "amend": kwargs.get("amend", 0),
        "print": kwargs.get("print_permission", kwargs.get("print", 0)),
        "email": kwargs.get("email", 0),
        "report": kwargs.get("report", 0),
        "import": kwargs.get("import_permission", kwargs.get("import", 0)),
        "export": kwargs.get("export", 0),
        "share": kwargs.get("share", 0)
    }

	if perm:
		doc = frappe.get_doc("Custom DocPerm", perm)
		doc.update(permission_data)
		doc.save(ignore_permissions=True)
	else:
         doc = frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": role,
            **permission_data
        })
         doc.insert(ignore_permissions=True)



def setup_roles_and_permissions():
    roles = ["Technician", "Spectrum PS User"]
    for role in roles:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({
                "doctype":"Role",
                "role_name":role,
                "desk_access":1
			}).insert(ignore_permissions=True)
    add_custom_permission("Sales Order", "Technician", read=1, write=1,export=1)
    add_custom_permission("Raven Channel", "Technician", read=1, write=1,create=1)
    add_custom_permission("Raven User", "Technician", read=1, write=1,create=1, delete=1)
    add_custom_permission("Raven Workspace Member", "Technician", read=1, write=0, export=1)
    add_custom_permission("Customer", "Technician", read=1, write=0,create=0, export=1)

    frappe.db.commit()
