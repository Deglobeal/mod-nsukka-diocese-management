# Project structure and coding conventions

## Scope
Django backend for the Man of Order and Discipline Movement of Nigeria — Nsukka Diocese Membership Management System. The initial deployment is diocese-scoped, while the data model must leave room for future state/national integration.

## Rules
- **One model per file.** Models live in each app's `models/` package (for example, `models/member.py` and `models/member_assignment.py`). Import public models in `models/__init__.py` so Django discovers them.
- **One view per file.** Views live in each app's `views/` package (for example, `views/public_member_profile_view.py`). Avoid a single giant `views.py`.
- Put business workflows in `services/`; complex read/query logic in `selectors/`.
- Keep app URL routes in each app's `urls.py`.
- Add tests under each app's `tests/` package, with descriptive test modules.
- Do not put secrets in source control. Use `.env` locally and deployment environment variables in production.
- Do not expose medical records through public member pages or public membership QR codes. Emergency access must be server-authorized, revocable, rate-limited, and audited.
- No actual member or medical data belongs in fixtures, commits, test output, or repository documentation.

## Apps
- `core`: homepage and shared infrastructure.
- `organizations`: diocese → deanery → parish → optional station.
- `members`: member identity and public profile.
- `verification`: registration and staged verification.
- `identity_cards`: official ID, short uniform ID, QR tokens, card issuance.
- `medical`: restricted emergency medical profile and emergency-code access.
- `accounts`: staff users, roles and permissions.
- `complaints`: private complaints and case workflows.
- `recognition`: recognition recommendations and promotion workflow.
- `transfers`: membership transfer workflow and history.
- `audit`: audit events.
- `notifications`: email/SMS and other delivery records.

## Initial implementation sequence
1. Agree the domain model and identifiers before writing models.
2. Define one model per file and import each through its app's `models/__init__.py`.
3. Add model constraints and tests before the first migration.
4. Implement member verification and public profile.
5. Implement emergency code lifecycle and private medical access.
6. Add permissions, audit events, backup/recovery and operational controls.
