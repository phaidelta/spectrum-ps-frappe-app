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

	original_user = frappe.session.user

	try:
		# Switch user temporarily for permission checks
		frappe.set_user(user)

		yield
	finally:
		# Revert back to the original user
		frappe.set_user(original_user)
