class NonExistentCustomerError(Exception):
	pass


class NoActiveSalesOrdersException(Exception):
	def __init__(self, customer, *args):
		super().__init__(*args)
		self.customer = customer
