# Schema checks

`rls_isolation.sql` proves that tenant isolation comes from the database, not
from application code: a merchant cannot read or write another merchant's rows
even if the query says otherwise.

It runs against a throwaway Postgres rather than your real project, so it can
insert users and assert freely.

```bash
docker run -d --name recover-pgcheck -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:15
until docker exec recover-pgcheck pg_isready -U postgres; do sleep 1; done

for f in supabase/tests/auth_stub.sql \
         supabase/migrations/20260101000000_initial_schema.sql \
         supabase/tests/rls_isolation.sql; do
  docker exec -i recover-pgcheck psql -U postgres -v ON_ERROR_STOP=1 -q < "$f"
done

docker rm -f recover-pgcheck
```

The last line printed should be `ALL RLS CHECKS PASSED`.

`auth_stub.sql` recreates the few Supabase objects the migration leans on —
`auth.users`, `auth.uid()`, `auth.role()`, and the `authenticated` role. Do not
run it against a real Supabase project; those objects already exist there.
