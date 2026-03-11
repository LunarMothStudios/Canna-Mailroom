# Security Notes

## Current MVP permissions

OAuth scopes currently requested:

- `https://mail.google.com/` (full Gmail access)
- `https://www.googleapis.com/auth/drive` (full Drive access)
- `https://www.googleapis.com/auth/documents` (Docs access)

This is intentionally broad for fast prototyping.

## Immediate safety practices

- Use a **dedicated agent Gmail account**, not personal inbox.
- Keep `credentials.json`, `token.json`, and `.env` out of git.
- Restrict local machine access where the service runs.
- Prefer a dedicated Drive folder for agent activity.

## Recommended hardening next

1. Scope minimization
   - Replace full Gmail scope with narrower scopes where possible.
   - Restrict Drive access pattern to approved folder IDs.

2. Outbound controls
   - Add recipient allowlist mode
   - Add human-approval gate before send
   - Add message signing/footers to make AI replies explicit

3. Auditability
   - Persist outbound events with timestamps and recipients
   - Keep trace of tool calls and doc IDs touched

4. Secret management
   - Move secrets to keychain/secret manager for non-local deployment
   - Rotate OpenAI keys and OAuth tokens periodically

5. Abuse prevention
   - Rate limits on outbound replies
   - Per-thread cooldowns
   - Block automated loops with other bots

## Threat model summary

Main risks in this MVP:
- Overbroad data access (mailbox + drive)
- Unreviewed outbound email generation
- Prompt-injection style content in inbound emails

Current status: acceptable for controlled local testing; not yet enterprise-safe.
