from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4")
    agent_email: str = os.getenv("AGENT_EMAIL", "")
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "20"))
    state_db: str = os.getenv("STATE_DB", "./state.db")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "./token.json")
    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "./credentials.json")
    google_drive_default_folder_id: str = os.getenv("GOOGLE_DRIVE_DEFAULT_FOLDER_ID", "")
    system_prompt_file: str = os.getenv("SYSTEM_PROMPT_FILE", "./SYSTEM_PROMPT.md")

    retry_max_attempts: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    retry_base_delay_ms: int = int(os.getenv("RETRY_BASE_DELAY_MS", "800"))
    retry_max_delay_ms: int = int(os.getenv("RETRY_MAX_DELAY_MS", "8000"))
    retry_jitter_ms: int = int(os.getenv("RETRY_JITTER_MS", "250"))


settings = Settings()
