from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


def normalize_sender_policy_mode(raw_value: str | None) -> str:
    candidate = (raw_value or "allowlist").strip().lower()
    if candidate in {"all", "allowlist"}:
        return candidate
    return "allowlist"


def normalize_order_provider(raw_value: str | None) -> str:
    candidate = (raw_value or "manual").strip().lower()
    if candidate in {"manual", "dutchie", "treez", "jane", "bridge", "custom"}:
        return candidate
    return "manual"


def normalize_knowledge_provider(raw_value: str | None) -> str:
    candidate = (raw_value or "manual").strip().lower()
    if candidate == "manual":
        return candidate
    return "manual"


def parse_csv_emails(raw_value: str | None) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for chunk in (raw_value or "").replace("\n", ",").split(","):
        email_value = chunk.strip().lower()
        if not email_value or email_value in seen:
            continue
        seen.add(email_value)
        ordered.append(email_value)
    return tuple(ordered)


@dataclass
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4")
    mail_provider: str = os.getenv("MAIL_PROVIDER") or "google_api"
    agent_email: str = os.getenv("AGENT_EMAIL", "")
    sender_policy_mode: str = normalize_sender_policy_mode(os.getenv("SENDER_POLICY_MODE", "allowlist"))
    allowed_senders: tuple[str, ...] = parse_csv_emails(os.getenv("ALLOWED_SENDERS", ""))
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "20"))
    state_db: str = os.getenv("STATE_DB", "./state.db")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "./token.json")
    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "./credentials.json")
    order_provider: str = normalize_order_provider(os.getenv("ORDER_PROVIDER", "manual"))
    order_provider_factory: str = os.getenv("ORDER_PROVIDER_FACTORY", "")
    knowledge_provider: str = normalize_knowledge_provider(os.getenv("KNOWLEDGE_PROVIDER", "manual"))
    store_knowledge_file: str = os.getenv("STORE_KNOWLEDGE_FILE", "./examples/store_knowledge.sample.json")
    manual_order_file: str = os.getenv("MANUAL_ORDER_FILE", "./examples/manual_orders.sample.json")
    dutchie_location_key: str = os.getenv("DUTCHIE_LOCATION_KEY", "") or os.getenv("DUTCHIE_API_KEY", "")
    dutchie_integrator_key: str = os.getenv("DUTCHIE_INTEGRATOR_KEY", "")
    dutchie_api_base_url: str = os.getenv("DUTCHIE_API_BASE_URL", "https://api.pos.dutchie.com")
    treez_dispensary: str = os.getenv("TREEZ_DISPENSARY", "")
    treez_client_id: str = os.getenv("TREEZ_CLIENT_ID", "")
    treez_api_key: str = os.getenv("TREEZ_API_KEY", "")
    treez_api_base_url: str = os.getenv("TREEZ_API_BASE_URL", "https://api.treez.io")
    bridge_order_provider_url: str = os.getenv("BRIDGE_ORDER_PROVIDER_URL", "")
    bridge_order_provider_token: str = os.getenv("BRIDGE_ORDER_PROVIDER_TOKEN", "")
    bridge_order_provider_source: str = os.getenv("BRIDGE_ORDER_PROVIDER_SOURCE", "bridge")
    bridge_order_provider_timeout_seconds: int = int(os.getenv("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS", "15"))
    jane_bridge_url: str = os.getenv("JANE_BRIDGE_URL", "")
    jane_bridge_token: str = os.getenv("JANE_BRIDGE_TOKEN", "")
    jane_bridge_timeout_seconds: int = int(os.getenv("JANE_BRIDGE_TIMEOUT_SECONDS", os.getenv("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS", "15")))
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
