from contextlib import contextmanager

import frappe


@contextmanager
def ignore_permissions():
	"""
	Temporarily switches off permission checks for the execution block
	and reliably restores the initial flag configuration afterward.
	"""
	# Capture the original state
	original_state = frappe.flags.ignore_permissions

	try:
		frappe.flags.ignore_permissions = True
		yield
	finally:
		# Guarantee the state is restored even if an exception occurs
		frappe.flags.ignore_permissions = original_state
