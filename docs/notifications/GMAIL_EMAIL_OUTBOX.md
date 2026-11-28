# Gmail API email notifications

The membership notification system uses a database outbox and a server-side Gmail API sender. It does not replace Django's configured SMTP backend. The sender account is `deglobeal@gmail.com`; the only requested Gmail scope is `https://www.googleapis.com/auth/gmail.send`.

## Local OAuth configuration

The defaults point outside the repository:

```text
~/.config/mod-nsukka/credentials.json
~/.config/mod-nsukka/token.json
```

Override with environment variables when needed:

```text
GMAIL_OAUTH_CREDENTIALS_FILE=/secure/path/credentials.json
GMAIL_OAUTH_TOKEN_FILE=/secure/path/token.json
GMAIL_API_SENDER=deglobeal@gmail.com
GMAIL_API_ENABLED=False
```

For serverless production environments, the OAuth client and authorized-user
JSON may instead be supplied through the secret environment variables
`GMAIL_OAUTH_CREDENTIALS_JSON` and `GMAIL_OAUTH_TOKEN_JSON`. Set both values;
the application refreshes access tokens in memory and does not write secrets to
the deployment filesystem. Production enables Gmail sending by default, and
forces Gmail sending on so an old or accidental `GMAIL_API_ENABLED=False`
environment value cannot silently leave new registration messages queued.
Registration emails are dispatched immediately after the registration
transaction commits. Local development continues to use `GMAIL_API_ENABLED`
to control sending.
Delivery failures remain visible in the email outbox and never roll back a
saved registration.

The Vercel production deployment also runs the outbox retry endpoint once per
day at 07:00 UTC. `CRON_SECRET` must be set as a sensitive production variable;
the endpoint rejects calls without the matching bearer token. Vercel Hobby
supports daily cron execution only, so retries scheduled sooner by the outbox
backoff are picked up by the next daily run. Pro and Enterprise can use a more
frequent schedule if the project plan supports it.

Keep both OAuth files outside the repository and media directories. Restrict filesystem access to the application operator. The application checks paths before loading them; it never prints their contents. The worker refreshes expired access tokens and atomically writes a refreshed token file with owner-only permissions. Production must use its own secret mount or protected persistent secret store; do not copy a developer's local token file to a production host.

The sender also embeds the approved `static/images/branding/mainmodlogo.jpg` crest as a CID image, so recipients do not need access to a development filesystem or a publicly hosted static file.

## OAuth testing and production readiness

The Google Cloud project is currently in OAuth Testing mode. For an external consent screen, refresh tokens issued in Testing expire after seven days, except when the only requested scopes are basic identity scopes. Gmail send is outside that exception. The worker reports refresh failure and marks the notification failed; reauthorize the account to restore sending. See Google's [OAuth refresh token expiration guidance](https://developers.google.com/identity/protocols/oauth2#expiration) and [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes).

Before production:

1. Use a production Google Cloud project and publish its OAuth consent screen to In production.
2. Complete the required verification for the sensitive `gmail.send` scope, including the consent-screen details and any Google review requirements.
3. Reauthorize the actual sending account in that production project and store its resulting OAuth client and token JSON in production-only secrets. On Vercel, use `GMAIL_OAUTH_CREDENTIALS_JSON` and `GMAIL_OAUTH_TOKEN_JSON`; do not add them to the repository.
4. Set `GMAIL_API_SENDER`. Production enables automatic registration email delivery; `GMAIL_API_ENABLED` does not disable Production delivery.
5. Confirm server egress to Google's OAuth and Gmail API endpoints. The registration request dispatches the applicant and sponsor messages after commit; other queued notices still use the supervised outbox worker.
6. Review Gmail account sending limits and quota responses. Gmail API acceptance is not proof of inbox delivery; the outbox records only the Gmail message ID and acceptance time.

Google classifies `gmail.send` as sensitive and documents additional OAuth verification for public apps using sensitive scopes ([Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [OAuth sensitive-scope review](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)). Gmail's sending quotas and service limits apply; this implementation backs off on retryable quota and service errors and does not claim unlimited sending.

## Outbox processing

Queue rows are created transactionally with registration or review decisions and carry an idempotency key. The worker claims one row at a time, records attempts, retries transient errors with exponential backoff capped at six hours, and fails permanent errors. If a send request times out after it starts or a worker lease goes stale, the row moves to administrator review because Gmail may already have accepted the message; the worker does not automatically resend an uncertain message. Administrators can inspect status, recipient, attempt count, Gmail message ID, and safe error summaries in Django Admin under Email Notifications. The template context, including sponsor bearer URLs, is hidden from the admin detail page and bearer URLs are discarded after Gmail acceptance.

Manual outbox processing is simulation only by default:

```sh
python manage.py process_email_outbox --simulate
```

Actual sends require both `GMAIL_API_ENABLED=True` and explicit `--send`:

```sh
python manage.py process_email_outbox --send --batch-size 25
```

For a supervised worker, schedule the latter command at an operationally appropriate interval only after production OAuth approval and controlled recipient verification. Never use it as an unreviewed test command.

Template-only previews use dummy values and never send mail:

```sh
python manage.py preview_email_templates
```

## Registration PDF attachment

At send time, the worker calls the existing membership registration PDF builder and existing Chaplain and optional Society/Organization letter builders, then combines their generated pages into one application-specific PDF named `MOD_COMPLETE_REGISTRATION_[APPLICATION_REFERENCE].pdf`. It does not read private files by guessed paths or reuse another application's documents. The PDF merger is provided by `pypdf`, listed in `requirements/base.txt`. If any required builder fails, the worker records a safe failure instead of sending an incomplete attachment.

## Recipient and decision rules

- Applicant messages use `MembershipApplication.email`.
- Sponsor messages use `MemberProfile.email` belonging to the verified active sponsor. A missing/invalid sponsor email creates a visible failed outbox record and never falls back to the applicant's address.
- Parish/Deanery completion messages are created only after the corresponding approved transition.
- Diocese approval/rejection uses the persisted final decision. A Membership ID is included only if the existing identity record exists at enqueue time.
- Additional-information messages use the existing one-time correction URL and expiry when `PUBLIC_BASE_URL` is configured. Otherwise the notification is marked failed for administrator attention.

Chairman activation email settings and flows are independent; `CHAIRMAN_ACTIVATION_EMAIL_ENABLED` remains unchanged.
