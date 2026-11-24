# PostgreSQL deployment and operations

PostgreSQL is the only supported database engine. Development, local settings,
automated tests, staging, production, management commands, and workers use the
PostgreSQL backend. No Django settings module falls back to SQLite.

## Local PostgreSQL setup

Install PostgreSQL 15 or newer using the operating-system package manager, then
start its service. For a local Homebrew installation on macOS:

```bash
brew install postgresql@16
brew services start postgresql@16
```

Create separate application and test roles/databases. The test role requires
`CREATEDB` for Django's standard test database lifecycle:

```sql
CREATE ROLE mod_app LOGIN PASSWORD 'set-a-local-password';
CREATE DATABASE mod_nsukka OWNER mod_app;
CREATE ROLE mod_test LOGIN CREATEDB PASSWORD 'set-a-separate-test-password';
```

Run SQL as a PostgreSQL administrator, for example with `psql postgres`. Keep
real passwords in `.env` or a secret manager; never copy them into source files.

## Environment variables

Copy `.env.example` to `.env` and set these PostgreSQL connection values:

| Variable | Purpose |
| --- | --- |
| `DB_NAME` | Development, staging or production database name |
| `DB_USER` | PostgreSQL application role |
| `DB_PASSWORD` | Role password (the variable must be present; an empty value is allowed for local trust authentication) |
| `DB_HOST` | PostgreSQL host or socket directory |
| `DB_PORT` | PostgreSQL port; defaults to `5432` |
| `DB_SSLMODE` | libpq SSL mode; local default is `prefer`, production should use `require` or the provider's required mode |
| `DB_CONN_MAX_AGE` | Persistent connection lifetime in seconds; production serverless defaults to `0` |
| `TEST_DB_NAME` | Dedicated test database; must begin with `test_` |
| `TEST_DB_USER` | Dedicated test role with `CREATEDB`, or access to a pre-provisioned test database |
| `TEST_DB_PASSWORD` | Test role password |
| `TEST_DB_HOST` | PostgreSQL test service host |
| `TEST_DB_PORT` | PostgreSQL test service port; defaults to `5432` |
| `TEST_DB_SSLMODE` | SSL mode for the isolated test service |

Production may use `DATABASE_URL` (`postgres://` or `postgresql://`) instead of
the `DB_*` values. The URL is validated and rejected if it names another engine.
Never set production `DATABASE_URL` as a test connection: tests exclusively
read `TEST_DB_*` values, and their database name is required to have the `test_`
prefix.

`config/settings/local_settings.py` is a developer-local, Git-ignored override.
It imports the PostgreSQL development settings and may adjust non-database local
options; it must not define a different database backend.

## Create the test database

The normal command automatically selects the isolated test settings module:

```bash
python manage.py test
```

Django creates and destroys the configured `TEST_DB_NAME`. The test settings
use `TEST_DB_MAINTENANCE_DATABASE` (default `postgres`) only to establish the
test database; test cases run against the separate `TEST_DB_NAME`. The
PostgreSQL test role must be able to create databases. If that permission is
unavailable, pre-provision the test database as an administrator and grant the
test role ownership:

```sql
CREATE DATABASE test_mod_nsukka OWNER mod_test;
```

Keep `TEST_DB_NAME` set to `test_mod_nsukka` and run `python manage.py test
--keepdb` when the role cannot create or drop databases. The test runner resets
the test database schema/data as part of its isolated test lifecycle. Never
point `TEST_DB_*` at a development or production database name.

CI uses a disposable PostgreSQL 16 service with a test-only role. No SQLite
service or SQLite test settings are present.

## Migrations and database operations

First confirm the configured engine and target database without printing
credentials:

```bash
python manage.py shell -c 'from django.conf import settings; db=settings.DATABASES["default"]; print(db["ENGINE"], db.get("TEST", {}).get("NAME", db["NAME"]), db["HOST"], db["PORT"])'
python manage.py showmigrations
python manage.py makemigrations --check
```

For a new development database, apply reviewed migrations with:

```bash
python manage.py migrate
```

Back up the intended PostgreSQL database before production schema changes:

```bash
set -a
. ./.env
set +a
mkdir -p backups
PGPASSWORD="$DB_PASSWORD" pg_dump \
  --host="$DB_HOST" --port="${DB_PORT:-5432}" --username="$DB_USER" \
  --format=custom \
  --file="backups/mod_nsukka-$(date +%Y%m%d-%H%M%S).dump" "$DB_NAME"
```

Restore a backup to a separately created recovery database first, then validate
the restored application before any cutover:

```bash
createdb mod_nsukka_restore
pg_restore --no-owner --dbname=mod_nsukka_restore backups/mod_nsukka.dump
```

Do not use SQLite files as a data migration source without a separately
reviewed, approved migration plan. Historical SQLite database files and backups
are retained as inert files; this change does not read, convert, or delete them.

## Production, staging, and workers

Set `DATABASE_URL` or the `DB_*` values in the platform's secret settings.
Production settings require valid PostgreSQL configuration and do not fall back
to local or SQLite databases. For TLS-managed PostgreSQL, set the provider's
recommended SSL mode (commonly `DB_SSLMODE=require`). Keep `DB_CONN_MAX_AGE=0`
for serverless deployments unless the provider explicitly supports persistent
connections.

Web processes, `manage.py` commands, notification outbox workers, and scheduled
tasks share the same Django database settings. Keep `DJANGO_SETTINGS_MODULE`
consistent with the environment (`config.settings.development` locally and
`config.settings.production` in deployment). Test commands are routed to
`config.settings.test` automatically unless an explicit `--settings` option is
provided.
