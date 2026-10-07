import frappe


def get_doc_or_none(*args, **kwargs):
	try:
		return frappe.get_doc(*args, **kwargs)
	except frappe.DoesNotExistError:
		pass

def get_cached_doc_or_none(*args, **kwargs):
	try:
		return frappe.get_cached_doc(*args, **kwargs)
	except frappe.DoesNotExistError:
		pass
