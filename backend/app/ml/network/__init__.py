"""Cross-merchant network intelligence.

Everything in this package reads across tenants, which makes it the one place
in the codebase where RLS is deliberately bypassed. That is the whole product
argument: no single merchant sees enough failed retries to tell a bank outage
from a bad afternoon, and pooling them is the only way anyone finds out in
time to stop burning RBI-limited retries into a gateway that is down.

The rule that keeps that defensible is that **aggregates go out, rows never
do**. Every function here reduces to a `(bank, method, hour)` cell before its
result leaves the module, and nothing that reaches an API response can be
traced back to which merchant contributed it.
"""
