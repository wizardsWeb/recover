# Recover — backend

FastAPI service. See the repository root `README.md` for the full quick start.

```bash
poetry install
cp .env.example .env      # then fill in your Supabase credentials
poetry run uvicorn app.main:app --reload --port 8000
poetry run pytest
poetry run ruff check app/
poetry run mypy app/
```
