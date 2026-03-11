# Troubleshooting

## OAuth browser flow does not open

- Ensure you're running locally with GUI access.
- Run `python scripts/auth_google.py` from activated venv.
- If remote/SSH, you may need alternative auth flow handling.

## `invalid_grant` / token issues

- Delete `token.json`
- Re-run auth script
- Ensure same OAuth client and same Google account

## `403` from Gmail/Drive/Docs APIs

- Verify corresponding API is enabled in Google Cloud project
- Verify OAuth consent and scopes are accepted
- Re-auth after changing scopes

## Agent doesn’t reply

- Check `GET /healthz` worker_alive=true
- Confirm inbound message is unread and not from agent itself
- Use `POST /process-now` to force immediate scan

## Wrong inbox/account

- Verify `AGENT_EMAIL` matches account authorized in OAuth flow
- Re-run OAuth with correct mailbox account

## Context not preserved across replies

- Ensure you are replying in the same Gmail thread
- Verify `state.db` exists and is writable
- Do not delete state between messages

## Replies are too slow

- Reduce `POLL_SECONDS`
- Use faster model in `.env` (`OPENAI_MODEL=gpt-5-mini` for speed)
- Keep system prompt concise

## Drive/Docs tool actions fail

- Check folder ID validity
- Confirm OAuth scope includes Drive + Docs
- Confirm account has access to target folder/docs
