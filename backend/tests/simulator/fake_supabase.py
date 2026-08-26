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
    },
    "customer_replies": {"customer_id": None, "llm_classification": None},
    "audit_events": {"case_id": None, "details": None, "trace_id": None},
}

#: Timestamp column each table orders by, filled in on insert.
_TIMESTAMP_COLUMNS: dict[str, str] = {
    "events": "received_at",
    "recovery_cases": "opened_at",
    "customer_replies": "received_at",
}


class _Result:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


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

    # -- operations ---------------------------------------------------------

    def select(self, columns: str = "*", **_: Any) -> _Query:
        self._op = "select"
        # `customers(name)` asks PostgREST to embed the related row.
        if "(" in columns:
            self._embed = columns[: columns.index("(")].rsplit(",", 1)[-1].strip()
        return self

    def insert(self, payload: Any, **_: Any) -> _Query:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any], **_: Any) -> _Query:
        self._op = "update"
        self._payload = payload
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

    def is_(self, column: str, value: Any) -> _Query:
        self._filters.append(("is", column, value))
        return self

    def limit(self, count: int) -> _Query:
        self._limit = count
        return self

    def order(self, column: str, desc: bool = False, **_: Any) -> _Query:
        self._order = (column, desc)
        return self

    # -- execution ----------------------------------------------------------

    def _read(self, row: dict[str, Any], column: str) -> Any:
        if "->>" in column:
            container, key = column.split("->>", 1)
            nested = row.get(container.strip()) or {}
            return _json_text(nested.get(key.strip()) if isinstance(nested, dict) else None)
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

        result = [dict(row) for row in matched]
        if self._embed:
            for row in result:
                related = self._db.find_one(self._embed, row.get(f"{self._embed[:-1]}_id"))
                row[self._embed] = {"name": related.get("name")} if related else None
        return _Result(result)


class FakeSupabase:
    """Holds the tables and hands out query builders."""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._clock = 0

    def table(self, name: str) -> _Query:
        return _Query(self, name)

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
