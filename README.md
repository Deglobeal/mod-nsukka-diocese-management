# M.O.D. Nsukka Diocese Membership Management System

Django 5.2 membership, verification, identity and diocesan administration platform.
PostgreSQL 15 or newer is required for local development, tests, staging and
production.

## Requirements

- Python 3.12+
- PostgreSQL 15+
- `psycopg` (included in the project requirements)

## Local setup

Install and start PostgreSQL, then create the development database and role. See
the [PostgreSQL setup guide](docs/deployment/POSTGRESQL.md) for commands and
permissions.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
cp .env.example .env
# Set the local PostgreSQL credentials in .env; do not commit .env.
python manage.py check
python manage.py migrate
```

All Django settings use the PostgreSQL backend. The settings fail with a clear
configuration error when required PostgreSQL connection details are missing;
there is no SQLite fallback.

## Tests

`python manage.py test` automatically selects `config.settings.test` and uses
the dedicated PostgreSQL database configured by `TEST_DB_*`. The test role
needs PostgreSQL `CREATEDB` permission so Django can create and remove
`test_mod_nsukka`. Tests never use `DATABASE_URL` or the development database
credentials.

```bash
python manage.py test
```

Continuous integration runs the same suite against an isolated PostgreSQL 16
service. See the [PostgreSQL setup guide](docs/deployment/POSTGRESQL.md) for
test-role and pre-provisioned-database options.

## Code organization

Every app uses `models/`, `views/`, `services/`, `selectors/`, and `tests/`
packages. See [`docs/architecture/PROJECT_STRUCTURE.md`](docs/architecture/PROJECT_STRUCTURE.md).

## Security baseline

- `.env` is ignored by Git; `.env.example` contains placeholders only.
- Production settings default to `DEBUG=False`.
- Medical data is intended to remain restricted and separate from public
  membership verification.
- Never commit member records, database credentials, passwords, emergency
  access codes, or medical information.
