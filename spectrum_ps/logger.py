import frappe


def get_logger():
	return frappe.logger("spectrum_ps", allow_site=True, file_count=50)
