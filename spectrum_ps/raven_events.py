"""Legacy Raven Message hooks. Outbound delivery is handled by Socket.IO."""


def on_raven_message_created(doc, method=None):
    # Intentionally unused. Do not send WhatsApp from the Raven Message DB hook,
    # otherwise Socket.IO and the DB hook can deliver the same message twice.
    return
