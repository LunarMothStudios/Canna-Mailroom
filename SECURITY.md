# Security Policy

## Supported versions

This repository is currently pre-1.0. Security fixes are applied to the latest `main` branch.

## Reporting a vulnerability

Please do **not** open public GitHub issues for security vulnerabilities.

Instead:
1. Email the maintainers directly (or org security contact)
2. Include reproduction steps and impact
3. Include affected commit/version if known

We will acknowledge reports as quickly as possible and coordinate remediation.

## Security considerations for this project

Because this project can read/send email and access Google Drive/Docs:
- run with a dedicated service mailbox
- restrict OAuth credentials and token file permissions
- rotate API keys and OAuth tokens
- avoid production use without allowlist and approval controls
