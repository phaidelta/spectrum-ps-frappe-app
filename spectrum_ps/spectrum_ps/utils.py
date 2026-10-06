from contextlib import contextmanager

import frappe

DEFAULT_ELEVATED_SER = "Administrator"


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


@contextmanager
def as_user(user: str | None = DEFAULT_ELEVATED_SER):
	"""
	Switch to a different user temporarily. Keep this as brief as possible to prevent attack vectors.

	Usage:
	```python
	with as_user("some user"):
		...
	```
	"""

	# Keep a snapshot of the original session user
	original_user = frappe.session.user

	try:
		# Switch user temporarily for permission checks. It only uses the user name
		frappe.session.user = user

		yield
	finally:
		# Restore original user
		frappe.session.user = original_user
