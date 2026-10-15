from .free_form_messages import *
from .logic_config import *
from .twilio_templates import *

INACTIVE_TICKET_STATUSES = ["Cancelled", "Paid"]
ALLOWED_PROVIDERS = frozenset({"google", "facebook"})
