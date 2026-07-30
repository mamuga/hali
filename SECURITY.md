# Security policy

## Reporting a vulnerability

Please do not open a public issue for security vulnerabilities. Email
martinmuga04@gmail.com directly with details. We aim to acknowledge
reports within 48 hours.

## Scope

HALI's public API has rate limiting and input validation on all write and
compute endpoints. Admin endpoints require an `X-Admin-Key` header,
compared using a constant-time HMAC comparison. Community-submitted
reports are resistant to poisoning via distinct-source thresholds that
must be met before any automatic severity escalation.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full security
model.

## Supported versions

This is an actively developed hackathon project; the `main` branch is the
only supported version at this time.

## Secrets

No credentials belong in this repository. `.env` is git-ignored and only
`.env.example`, which holds placeholders, is committed. The full commit
history has been scanned with `gitleaks` and by direct comparison against
live credential values; it is clean.

If you are deploying your own instance, generate your own values for every
key in `.env.example` rather than reusing the example defaults.
