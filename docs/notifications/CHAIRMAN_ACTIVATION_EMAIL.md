# Chairman activation email

Chairman account activation is sent immediately when a superuser issues or
reissues an activation link. The message includes the official M.O.D. email
header, appointment details, a secure activation button, the link expiry, and a
plain-text alternative. The link is single-use and expires 48 hours after a
delivery channel accepts it.

## SMTP configuration

Set these variables in the environment used by the Django web process:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-sender@example.com
EMAIL_HOST_PASSWORD=your-smtp-password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=M.O.D. Nsukka Diocese <your-sender@example.com>
CHAIRMAN_ACTIVATION_EMAIL_ENABLED=True
PUBLIC_BASE_URL=https://your-public-domain.example
```

Use the mail provider's required TLS/SSL settings and a sender address it
authorizes. Keep credentials in a secret manager or environment variables, not
in source control. Add the values to the deployment environment as well as to
local `.env`; changing local settings does not change Vercel's environment.

With email delivery enabled, issuing or reissuing an activation calls the
configured SMTP backend automatically. If delivery is disabled or fails, the
activation page records the channel state and the link remains unusable until a
channel accepts it. A successful reissue invalidates earlier unused links, so
only reissue when the new link should be sent.

`PUBLIC_BASE_URL` must be the site's origin only. A localhost URL is suitable
only when the recipient opens the message on the same computer running the
local server; use the deployed HTTPS site for Chairman access from another
device.
