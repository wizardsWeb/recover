"""A minimal in-memory stand-in for the Supabase client.

It implements the slice of the PostgREST fluent builder the simulator actually
uses — ``table(...).select(...).eq(...).execute()`` and friends — over plain
dicts. That is deliberately the *shape* of PostgREST and not its semantics:

* **It does not enforce RLS.** Nothing here could. Tenant isolation is a
  Postgres guarantee, and it is tested where it lives, in
  ``supabase/tests/rls_isolation.sql``. What these tests cover is that the
  simulator's own query logic is right — which merchant id it filters on, which
  rows reset deletes, whether a second load duplicates anything.
* **It does not validate the schema.** A column that does not exist will happily
  round-trip. Migrations are the schema's own test.

The alternative was a live Supabase project per test run. That gives higher
fidelity and costs a network round trip plus shared mutable state on every
assertion; for logic this deterministic it is a bad trade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

_EPOCH = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)

#: Column defaults the real schema applies, for the columns the simulator reads
#: back. Anything the code under test never looks at is intentionally absent.
_DEFAULTS: dict[str, dict[str, Any]] = {
    "customers": {
        "external_id": None,
        "name": None,
        "phone": None,
        "email": None,
        "ltv_cents": 0,
        "tenure_days": 0,
        "consent": {},
        "metadata": {},
    },
    "payment_methods": {"bin": None, "bank": None, "success_rate_90d": None, "metadata": {}},
    # Postgres hands these back as NULL on an insert that omits them; the fake
    # would otherwise leave the keys missing entirely, so code that reads
    # `row["outcome"]` passes here and raises KeyError against a real database.
    "uplift_holdouts": {
        "holdout_reason": None,
        "outcome": None,
        "outcome_amount_cents": None,
        "context_features": {},
        "used_in_training": False,
    },
    "uplift_model_snapshots": {
        "feature_importances": {},
        "bucket_uplifts": {},
        "training_sample_size": 0,
    },
    "events": {"customer_id": None, "processed_at": None},
    "recovery_cases": {
        "status": "open",
        "amount_recovered_cents": 0,
        "closed_at": None,
        "current_step": None,
        "diagnosis": None,
        "uplift_bucket": None,
        "is_holdout": False,
        "trigger_event_id": None,
        "metadata": {},
    },
    "customer_replies": {
        "customer_id": None,
        "llm_classification": None,
        "applied_state_update": None,
    },
    "agent_decisions": {
        "decision_source": None,
        "bandit_chosen_arm": None,
        "bandit_arm_confidence": None,
        "bandit_mode": None,
        "bandit_alternatives": None,
        "causal_path": None,
        "diagnosis_posteriors": None,
        "chosen_action": None,
        "action_params": None,
        "reasoning": None,
        "uplift_estimate": None,
        "guardrail_checks": None,
    },
    "execution_attempts": {
        "decision_id": None,
        "request_payload": None,
        "response_payload": None,
        "status": "pending",
        "idempotency_key": None,
        "completed_at": None,
    },
    "network_alerts": {
        "affected_bank": None,
        "affected_method": None,
        "resolved_at": None,
        "metadata": None,
        "z_score": None,
        "sample_size": None,
        "affected_merchants_count": None,
        "network_wide_success_rate": None,
        "baseline_rate": None,
    },
    "network_stats": {
        "merchant_size_class": None,
        "success_rate": 0.0,
        "sample_size": 0,
    },
    "audit_events": {"case_id": None, "details": None, "trace_id": None},
    "llm_cache": {
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": None,
        "hit_count": 0,
    },
}

#: Columns Postgres will refuse an insert without.
#:
#: The fake does not validate the schema in general — migrations are the
#: schema's own test — but NOT NULL on a foreign key is the one omission that
#: fails *silently* in this codebase, because several writers are deliberately
#: non-fatal. A batch run that never set `customer_id` inserted a hundred rows
#: here and zero in Postgres, reported success, and was only caught by probing
#: the live database by hand.
#:
#: Only the columns whose absence a real insert rejects. Adding every NOT NULL
#: column would turn this into a second copy of the schema to keep in step.
_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "recovery_cases": ("merchant_id", "customer_id", "playbook", "amount_at_risk_cents"),
    "agent_decisions": ("case_id", "merchant_id", "step_number", "step_name"),
    "execution_attempts": ("case_id", "merchant_id", "action_type", "adapter"),
    "customer_replies": ("case_id", "merchant_id", "channel", "raw_text"),
    "bandit_rewards": ("merchant_id", "case_id", "arm_name", "context_vector", "context_bucket"),
    "uplift_holdouts": ("case_id", "merchant_id"),
    "batch_runs": ("merchant_id", "n_cases"),
    "causal_edge_updates": ("merchant_id", "playbook", "from_node", "to_node"),
    "customers": ("merchant_id",),
    "events": ("merchant_id", "event_type"),
}

#: Timestamp column each table orders by, filled in on insert.
_TIMESTAMP_COLUMNS: dict[str, str] = {
    "events": "received_at",
    "recovery_cases": "opened_at",
    "customer_replies": "received_at",
    "execution_attempts": "attempted_at",
}


class _Result:
    def __init__(self, data: list[dict[str, Any]], count: int | None = None) -> None:
        self.data = data
        # PostgREST only populates `count` when the caller asked for it, and the
        # guardrail reads `resp.count or 0` — so leaving it None when unasked is
        # what keeps that idiom under test.
        self.count = count


def _json_text(value: Any) -> str:
    """Render a value the way Postgres's ``->>`` operator would.

    ``->>`` returns *text*, so a JSON boolean comes back as the string "true".
    Getting this wrong is exactly how a fixture-reset filter silently matches
    nothing, so the fake reproduces it rather than comparing Python truthiness.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


class _Query:
    """One accumulating query against one table."""

    def __init__(self, db: FakeSupabase, table: str) -> None:
        self._db = db
        self._table = table
        self._op = "select"
        self._filters: list[tuple[str, str, Any]] = []
        self._payload: Any = None
        self._limit: int | None = None
        self._order: tuple[str, bool] | None = None
        self._embed: str | None = None
        self._embed_columns: list[str] = []
        self._count: str | None = None
        self._range: tuple[int, int] | None = None
        self._on_conflict: str | None = None

    # -- operations ---------------------------------------------------------

    def select(self, *columns: str, **kwargs: Any) -> _Query:
        self._op = "select"
        self._count = kwargs.get("count")
        # `customers(name)` asks PostgREST to embed the related row; `customers(*)`
        # asks for all of its columns. The distinction matters — code reading an
        # embedded LTV would read zero against a fake that only ever returned the
        # name, and the test would pass while production disagreed.
        for column in columns:
            if "(" in column:
                self._embed = column[: column.index("(")].rsplit(",", 1)[-1].strip()
                inner = column[column.index("(") + 1 : column.rindex(")")]
                self._embed_columns = [c.strip() for c in inner.split(",") if c.strip()]
        return self

    def insert(self, payload: Any, **_: Any) -> _Query:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any], **_: Any) -> _Query:
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload: Any, **kwargs: Any) -> _Query:
        # `on_conflict` names the column PostgREST resolves the conflict on. The
        # fake honours it rather than ignoring it, because a test that passes
        # against an upsert-as-insert would hide a duplicate-key error that only
        # appears against a real UNIQUE constraint.
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = kwargs.get("on_conflict")
        return self

    def delete(self, **_: Any) -> _Query:
        self._op = "delete"
        return self

    # -- filters ------------------------------------------------------------

    def eq(self, column: str, value: Any) -> _Query:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self._filters.append(("in", column, list(values)))
        return self

    def neq(self, column: str, value: Any) -> _Query:
        self._filters.append(("neq", column, value))
        return self

    def gte(self, column: str, value: Any) -> _Query:
        self._filters.append(("gte", column, value))
        return self

    def lt(self, column: str, value: Any) -> _Query:
        self._filters.append(("lt", column, value))
        return self

    def is_(self, column: str, value: Any) -> _Query:
        self._filters.append(("is", column, value))
        return self

    def like(self, column: str, pattern: str) -> _Query:
        self._filters.append(("like", column, pattern))
        return self

    def limit(self, count: int) -> _Query:
        self._limit = count
        return self

    def range(self, start: int, end: int) -> _Query:
        # PostgREST's range is inclusive at both ends, like an HTTP Range header.
        self._range = (start, end)
        return self

    def order(self, column: str, desc: bool = False, **_: Any) -> _Query:
        self._order = (column, desc)
        return self

    # -- execution ----------------------------------------------------------

    def _read(self, row: dict[str, Any], column: str) -> Any:
        if "->>" in column:
            container, key = column.split("->>", 1)
            nested = row.get(container.strip()) or {}
            value = nested.get(key.strip()) if isinstance(nested, dict) else None
            # A key that is absent, or present as JSON null, reads as SQL NULL —
            # *not* as the text "null". The distinction is what makes
            # `is.null` work: it is how a filter excludes rows that never had
            # the key, which is how synthetic batch cases are kept out of every
            # read that reports money. Rendering it as text instead matches
            # nothing and silently disables the filter.
            return None if value is None else _json_text(value)
        return row.get(column)

    def _matches(self, row: dict[str, Any]) -> bool:
        for kind, column, value in self._filters:
            actual = self._read(row, column)
            if kind == "eq":
                if "->>" in column:
                    if actual != _json_text(value):
                        return False
                elif actual != value:
                    return False
            elif kind == "like":
                # Only the trailing-% form the audit filter uses is supported;
                # anything else would be a fake that lies about its coverage.
                prefix = str(value).rstrip("%")
                if actual is None or not str(actual).startswith(prefix):
                    return False
            elif kind == "neq":
                if actual == value:
                    return False
            elif kind == "gte":
                # Timestamps are compared as ISO strings, which sort correctly
                # only because every value the fake stores is UTC with the same
                # precision — the same assumption PostgREST's index relies on.
                if actual is None or str(actual) < str(value):
                    return False
            elif kind == "lt":
                if actual is None or str(actual) >= str(value):
                    return False
            elif kind == "in":
                if actual not in value:
                    return False
            elif kind == "is":
                wants_null = value in (None, "null")
                if (actual is None) is not wants_null:
                    return False
        return True

    def execute(self) -> _Result:
        rows = self._db.rows(self._table)

        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = [self._db.insert_row(self._table, dict(item)) for item in payload]
            return _Result(inserted)

        if self._op == "upsert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            written: list[dict[str, Any]] = []
            for item in payload:
                existing = None
                if self._on_conflict:
                    # PostgREST takes a comma-separated conflict target, and a
                    # composite one is the normal case for reference tables.
                    # Treating the whole string as a single column name would
                    # compare None to None on every row and match the first —
                    # so an upsert of forty nodes would overwrite one row forty
                    # times and report success.
                    keys = [key.strip() for key in self._on_conflict.split(",") if key.strip()]
                    existing = next(
                        (row for row in rows if all(row.get(key) == item.get(key) for key in keys)),
                        None,
                    )
                if existing is not None:
                    existing.update(item)
                    written.append(dict(existing))
                else:
                    written.append(self._db.insert_row(self._table, dict(item)))
            return _Result(written)

        matched = [row for row in rows if self._matches(row)]

        if self._op == "update":
            for row in matched:
                row.update(self._payload)
            return _Result([dict(row) for row in matched])

        if self._op == "delete":
            keep = [row for row in rows if row not in matched]
            self._db.replace(self._table, keep)
            return _Result([dict(row) for row in matched])

        if self._order:
            column, desc = self._order
            matched = sorted(matched, key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._range is not None:
            start, end = self._range
            matched = matched[start : end + 1]

        total = len(matched) if self._count else None
        result = [dict(row) for row in matched]
        if self._embed:
            for row in result:
                related = self._db.find_one(self._embed, row.get(f"{self._embed[:-1]}_id"))
                if related is None:
                    row[self._embed] = None
                elif "*" in self._embed_columns:
                    row[self._embed] = dict(related)
                else:
                    row[self._embed] = {c: related.get(c) for c in self._embed_columns}
        return _Result(result, total)


class FakeSupabase:
    """Holds the tables and hands out query builders."""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._clock = 0

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> _Rpc:
        """Dispatch to a Python re-implementation of a Postgres function.

        The functions in ``supabase/migrations`` are real SQL and cannot run
        here, so each one the app calls needs a stand-in. Modelling the
        *semantics* rather than raising means the tests exercise the code path
        the deployment actually takes — a fake that raised would send every test
        down the fallback branch and leave the RPC call itself untested.

        An unknown function raises, which is what makes a new RPC that nobody
        taught the fake about fail loudly here rather than silently in
        production.
        """
        handler = _RPC_HANDLERS.get(name)
        if handler is None:
            raise KeyError(f"FakeSupabase has no stand-in for rpc({name!r})")
        return _Rpc(lambda: handler(self, params))

    # -- storage ------------------------------------------------------------

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(table, [])

    def replace(self, table: str, rows: list[dict[str, Any]]) -> None:
        self._tables[table] = rows

    def find_one(self, table: str, row_id: Any) -> dict[str, Any] | None:
        return next((row for row in self.rows(table) if row.get("id") == row_id), None)

    def _next_timestamp(self) -> str:
        # Monotonic, so `order by received_at desc` is deterministic instead of
        # depending on how fast the test machine inserts rows.
        self._clock += 1
        return (_EPOCH + timedelta(seconds=self._clock)).isoformat()

    def insert_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        missing = [column for column in _REQUIRED_COLUMNS.get(table, ()) if row.get(column) is None]
        if missing:
            # Mirrors Postgres's 23502. Raised rather than logged, because the
            # writers that would swallow it are exactly the ones this exists to
            # catch — they report success having written nothing.
            raise ValueError(
                f'null value in column "{missing[0]}" of relation "{table}" '
                f"violates not-null constraint"
            )

        stamp = self._next_timestamp()
        stored: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            **_DEFAULTS.get(table, {}),
            **row,
            "created_at": stamp,
            "updated_at": stamp,
        }
        timestamp_column = _TIMESTAMP_COLUMNS.get(table)
        if timestamp_column and timestamp_column not in row:
            stored[timestamp_column] = stamp
        self.rows(table).append(stored)
        return dict(stored)

    # -- test conveniences --------------------------------------------------

    def count(self, table: str) -> int:
        return len(self.rows(table))

    def seed_merchant(self, merchant_id: str) -> None:
        self.rows("merchants").append({"id": merchant_id, "name": "Test Merchant"})


class _Rpc:
    """Defers a fake RPC until ``.execute()``, matching the client's shape."""

    def __init__(self, run: Any) -> None:
        self._run = run

    def execute(self) -> _Result:
        return _Result(self._run() or [])


def _increment_bandit_posterior(
    db: FakeSupabase, params: dict[str, Any]
) -> list[dict[str, Any]]:
    """``increment_bandit_posterior`` from 20260115000000_atomic_posterior.sql.

    Upsert on the table's UNIQUE tuple, incrementing rather than overwriting. The
    atomicity the real function provides is a Postgres guarantee and is not
    modelled — there is one thread here — but the arithmetic and the
    insert-versus-update split are, which is what the tests assert on.
    """
    rows = db.rows("bandit_posteriors")
    key = (
        params["p_merchant_id"],
        params["p_playbook"],
        params["p_arm_name"],
        params["p_context_bucket"],
    )
    alpha_inc = float(params["p_alpha_inc"])
    beta_inc = float(params["p_beta_inc"])

    for row in rows:
        if (
            row.get("merchant_id"),
            row.get("playbook"),
            row.get("arm_name"),
            row.get("context_bucket"),
        ) == key:
            row["alpha"] = float(row.get("alpha", 1.0)) + alpha_inc
            row["beta"] = float(row.get("beta", 1.0)) + beta_inc
            row["n_pulls"] = int(row.get("n_pulls", 0)) + 1
            return []

    db.insert_row(
        "bandit_posteriors",
        {
            "merchant_id": key[0],
            "playbook": key[1],
            "arm_name": key[2],
            "context_bucket": key[3],
            # The flat prior plus this observation, so a first success lands on
            # Beta(2,1) rather than on nothing.
            "alpha": 1.0 + alpha_inc,
            "beta": 1.0 + beta_inc,
            "n_pulls": 1,
        },
    )
    return []


_RPC_HANDLERS: dict[str, Any] = {
    "increment_bandit_posterior": _increment_bandit_posterior,
}
