# M.O.D. Nsukka Diocese Membership Management System

A Django project scaffold for the Man of Order and Discipline Movement of Nigeria, initially scoped to Nsukka Diocese.

## Status
**Scaffold only.** The application layout and app boundaries are created. Domain models, migrations, business workflows, authentication policy, and production deployment are intentionally not implemented yet; these will be designed in small, reviewable steps.

## Requirements
- Python 3.12+
- PostgreSQL 15+

## Local setup (macOS/Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
cp .env.example .env
# Edit .env with your local PostgreSQL database credentials.
python manage.py check
python manage.py test
```

No migrations for domain models are included yet. Once the database models are agreed and added, create migrations with `python manage.py makemigrations` and review them before applying with `python manage.py migrate`.

## Code organization
Every app uses `models/`, `views/`, `services/`, `selectors/`, and `tests/` packages. Keep each model and each view in its own file to make debugging and code review easier. See [`docs/architecture/PROJECT_STRUCTURE.md`](docs/architecture/PROJECT_STRUCTURE.md).

## Security baseline
- `.env` is ignored by Git; `.env.example` contains placeholders only.
- Production settings default to `DEBUG=False`.
- Medical data is intended to remain restricted and separate from public membership verification.
- Never commit real member data, emergency access codes, passwords, or medical information.
