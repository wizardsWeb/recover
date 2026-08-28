"""Learned models that sit beside the agent loop rather than inside it.

Nothing here runs on the request path. Training reads history and writes a
snapshot; the loop reads the snapshot. Keeping the two apart is what lets the
agent keep working when there is no model yet — which is its state on day one
for every new merchant.
"""
