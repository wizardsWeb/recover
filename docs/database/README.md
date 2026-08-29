# Database snapshots

Screenshots of the live Supabase project — schema and real rows.

Worth capturing, because each one backs a claim in the README:

| file | what it shows |
| --- | --- |
| `schema.png` | the table list, or the Supabase schema visualiser |
| `rls-policies.png` | row-level security enabled on every merchant-scoped table |
| `recovery-cases.png` | real case rows with status and amounts |
| `agent-decisions.png` | a `decide` row with its chosen arm and alternatives |
| `bandit-posteriors.png` | learned alpha/beta per context bucket |
| `audit-events.png` | the append-only decision trail |
| `network-stats.png` | pooled bank × method × hour rows |

`rls-policies.png` is the one a reviewer will actually look for — it is the
evidence that tenant isolation is enforced by Postgres rather than by
application code.
