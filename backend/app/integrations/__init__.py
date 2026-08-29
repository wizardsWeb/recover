"""Outbound integrations with third-party APIs.

One module per provider. Everything here is allowed to fail: an integration is
someone else's uptime, and a recovery agent that stops working because a
payment provider returned a 503 is worse than one that records what it would
have sent and carries on.
"""
