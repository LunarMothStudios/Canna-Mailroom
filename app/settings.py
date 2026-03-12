from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4")
    mail_provider: str = os.getenv("MAIL_PROVIDER") or "google_api"
    agent_email: str = os.getenv("AGENT_EMAIL", "")
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "20"))
    state_db: str = os.getenv("STATE_DB", "./state.db")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "./token.json")
    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "./credentials.json")
    google_drive_default_folder_id: str = os.getenv("GOOGLE_DRIVE_DEFAULT_FOLDER_ID", "")
    system_prompt_file: str = os.getenv("SYSTEM_PROMPT_FILE", "./SYSTEM_PROMPT.md")
    gog_account: str = os.getenv("GOG_ACCOUNT", "")
    gog_gmail_topic: str = os.getenv("GOG_GMAIL_TOPIC", "")
    gog_gmail_label: str = os.getenv("GOG_GMAIL_LABEL", "INBOX")
    gog_gmail_hook_token: str = os.getenv("GOG_GMAIL_HOOK_TOKEN", "")
    gog_gmail_push_token: str = os.getenv("GOG_GMAIL_PUSH_TOKEN", "")
    gog_gmail_hook_url: str = os.getenv("GOG_GMAIL_HOOK_URL", "http://127.0.0.1:8787/hooks/gmail")
    gog_gmail_serve_bind: str = os.getenv("GOG_GMAIL_SERVE_BIND", "127.0.0.1")
    gog_gmail_serve_port: int = int(os.getenv("GOG_GMAIL_SERVE_PORT", "8788"))
    gog_gmail_serve_path: str = os.getenv("GOG_GMAIL_SERVE_PATH", "/gmail-pubsub")
    gog_gmail_include_body: bool = (os.getenv("GOG_GMAIL_INCLUDE_BODY", "true").strip().lower() not in {"0", "false", "no"})
    gog_gmail_max_bytes: int = int(os.getenv("GOG_GMAIL_MAX_BYTES", "20000"))
    gog_gmail_renew_every_minutes: int = int(os.getenv("GOG_GMAIL_RENEW_EVERY_MINUTES", "720"))

    retry_max_attempts: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    retry_base_delay_ms: int = int(os.getenv("RETRY_BASE_DELAY_MS", "800"))
    retry_max_delay_ms: int = int(os.getenv("RETRY_MAX_DELAY_MS", "8000"))
    retry_jitter_ms: int = int(os.getenv("RETRY_JITTER_MS", "250"))


settings = Settings()
