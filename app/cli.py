from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import textwrap
import webbrowser


GOOGLE_SETUP_URLS = {
    "Gmail API": "https://console.cloud.google.com/apis/library/gmail.googleapis.com",
    "OAuth branding": "https://console.cloud.google.com/auth/branding",
    "OAuth audience": "https://console.cloud.google.com/auth/audience",
    "OAuth clients": "https://console.cloud.google.com/auth/clients",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def detect_repo_root() -> Path:
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])
    package_root = Path(__file__).resolve().parent.parent
    candidates.extend([package_root, *package_root.parents])

    for candidate in candidates:
        if (candidate / ".env.example").exists() and (candidate / "app").exists():
            return candidate

    return package_root


REPO_ROOT = detect_repo_root()


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env_file(path: Path, values: dict[str, str]):
    example_path = REPO_ROOT / ".env.example"
    ordered_keys: list[str] = []
    if example_path.exists():
        for raw_line in example_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in raw_line:
                continue
            key, _ = raw_line.split("=", 1)
            ordered_keys.append(key.strip())

    for key in values:
        if key not in ordered_keys:
            ordered_keys.append(key)

    output = "\n".join(f"{key}={values.get(key, '')}" for key in ordered_keys) + "\n"
    path.write_text(output)


def resolve_runtime_path(raw_value: str | None, default_relative_path: str) -> Path:
    value = raw_value or default_relative_path
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def ensure_env_file() -> tuple[Path, dict[str, str]]:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        shutil.copyfile(REPO_ROOT / ".env.example", env_path)
        print(f"Created {env_path}")
    return env_path, parse_env_file(env_path)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def normalize_mail_provider(raw_value: str | None) -> str:
    candidate = (raw_value or "").strip().lower()
    if candidate in {"google", "google_api"}:
        return "google_api"
    if candidate == "gog":
        return "gog"
    return candidate or "google_api"


def prompt_mail_provider(default: str | None = None) -> str:
    while True:
        provider = normalize_mail_provider(
            prompt("Mail provider (google_api or gog)", default=default or "google_api", required=True)
        )
        if provider in {"google_api", "gog"}:
            return provider
        print("Choose `google_api` or `gog`.")


def normalize_sender_policy_mode(raw_value: str | None) -> str:
    candidate = (raw_value or "").strip().lower()
    if candidate in {"all", "allowlist"}:
        return candidate
    return candidate or "all"


def normalize_order_provider(raw_value: str | None) -> str:
    candidate = (raw_value or "").strip().lower()
    if candidate in {"manual", "dutchie", "treez", "jane", "bridge", "custom"}:
        return candidate
    return candidate or "manual"


def prompt_order_provider(default: str | None = None) -> str:
    while True:
        provider = normalize_order_provider(
            prompt("Order provider (manual, dutchie, treez, jane, bridge, or custom)", default=default or "manual", required=True)
        )
        if provider in {"manual", "dutchie", "treez", "jane", "bridge", "custom"}:
            return provider
        print("Choose `manual`, `dutchie`, `treez`, `jane`, `bridge`, or `custom`.")


def normalize_knowledge_provider(raw_value: str | None) -> str:
    candidate = (raw_value or "").strip().lower()
    if candidate == "manual":
        return candidate
    return candidate or "manual"


def prompt_knowledge_provider(default: str | None = None) -> str:
    while True:
        provider = normalize_knowledge_provider(
            prompt("Knowledge provider (manual only for now)", default=default or "manual", required=True)
        )
        if provider == "manual":
            return provider
        print("Choose `manual`.")


def prompt_sender_policy_mode(default: str | None = None) -> str:
    while True:
        mode = normalize_sender_policy_mode(
            prompt("Sender policy mode (all or allowlist)", default=default or "all", required=True)
        )
        if mode in {"all", "allowlist"}:
            return mode
        print("Choose `all` or `allowlist`.")


def prompt(
    label: str,
    *,
    default: str | None = None,
    secret: bool = False,
    required: bool = False,
) -> str:
    while True:
        if secret and default:
            suffix = " [saved]"
        else:
            suffix = f" [{default}]" if default else ""
        raw = (
            getpass.getpass(f"{label}{suffix}: ")
            if secret
            else input(f"{label}{suffix}: ")
        ).strip()
        if raw:
            return raw
        if default is not None:
            return default
        if not required:
            return ""
        print("This value is required.")


def looks_like_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))


def prompt_email(label: str, *, default: str | None = None, required: bool = False) -> str:
    while True:
        value = prompt(label, default=default, required=required)
        if not value and not required:
            return value
        if looks_like_email(value):
            return value
        print("Enter a real email address, for example `agent@example.com`.")


def confirm(prompt_text: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input(f"{prompt_text} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def print_header(title: str):
    print()
    print(title)
    print("=" * len(title))


def validate_desktop_oauth_client(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"Missing file: {path}"

    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as err:
        return False, f"Invalid JSON in {path}: {err}"

    installed = payload.get("installed")
    if not isinstance(installed, dict):
        return False, "Expected a desktop OAuth client JSON with an 'installed' object."

    required_keys = {"client_id", "client_secret", "auth_uri", "token_uri"}
    missing = sorted(required_keys - set(installed))
    if missing:
        return False, f"OAuth client JSON is missing keys: {', '.join(missing)}"

    return True, "Desktop OAuth client looks valid."


def validate_import_path(raw_value: str | None) -> tuple[bool, str]:
    raw = (raw_value or "").strip()
    if not raw:
        return False, "missing import path"

    module_name = ""
    attr_name = ""
    if ":" in raw:
        module_name, attr_name = raw.split(":", 1)
    elif "." in raw:
        module_name, attr_name = raw.rsplit(".", 1)
    else:
        return False, "expected `module:attribute` or `module.attribute`"

    try:
        module = importlib.import_module(module_name)
    except Exception as err:
        return False, f"failed to import module `{module_name}`: {err}"

    if not hasattr(module, attr_name):
        return False, f"module `{module_name}` does not define `{attr_name}`"
    return True, f"{module_name}:{attr_name}"


def open_google_setup_urls():
    for name, url in GOOGLE_SETUP_URLS.items():
        print(f"Opening {name}: {url}")
        webbrowser.open_new_tab(url)


def run_subprocess(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, cwd=str(cwd), env=env, check=False).returncode


def run_logged_subprocess(command: list[str], *, cwd: Path = REPO_ROOT) -> int:
    print(f"$ {shlex.join(command)}")
    return run_subprocess(command, cwd=cwd)


def run_google_auth() -> int:
    print_header("Google Auth")
    print("Running the Google OAuth flow now.")
    return run_subprocess([sys.executable, "scripts/auth_google.py"], cwd=REPO_ROOT)


def detect_gcloud_project() -> str | None:
    if not command_exists("gcloud"):
        return None
    result = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True,
        text=True,
        check=False,
    )
    value = (result.stdout or "").strip()
    if result.returncode != 0 or not value or value == "(unset)":
        return None
    return value


def parse_gcp_topic(raw_value: str | None) -> tuple[str, str] | None:
    raw = (raw_value or "").strip()
    if not raw.startswith("projects/") or "/topics/" not in raw:
        return None
    prefix, topic_name = raw.split("/topics/", 1)
    project_id = prefix.replace("projects/", "", 1).strip()
    topic_name = topic_name.strip()
    if not project_id or not topic_name:
        return None
    return project_id, topic_name


def complete_google_api_setup(env_values: dict[str, str]) -> int:
    credentials_path = resolve_runtime_path(env_values.get("GOOGLE_CREDENTIALS_FILE"), "./credentials.json")
    token_path = resolve_runtime_path(env_values.get("GOOGLE_TOKEN_FILE"), "./token.json")

    print_header("Google OAuth Client")
    wait_for_credentials_file(credentials_path)

    print_header("Google Sign-In")
    if token_path.exists():
        print(f"Token file already exists: {token_path}")
        should_auth = confirm("Re-run the Google sign-in flow?", default=False)
    else:
        should_auth = confirm("Run the Google sign-in flow now?", default=True)

    if should_auth:
        exit_code = run_google_auth()
        if exit_code != 0:
            print("Google auth did not complete successfully.")
            return exit_code

    print_header("Setup Complete")
    print("Next commands:")
    print("1. mailroom doctor")
    print("2. mailroom run --reload")
    print("3. curl http://127.0.0.1:8787/healthz")
    print()
    print("For an end-to-end email test, send a message from a different mailbox to:")
    print(f"   {env_values['AGENT_EMAIL']}")
    return 0


def configure_sender_policy(env_path: Path, env_values: dict[str, str]) -> dict[str, str]:
    print_header("Mailroom Access")
    print("Choose whether the agent replies to everyone or only to an explicit allowlist.")

    env_values["SENDER_POLICY_MODE"] = prompt_sender_policy_mode(env_values.get("SENDER_POLICY_MODE"))
    env_values["ALLOWED_SENDERS"] = prompt(
        "Allowed sender emails (comma-separated, used only in allowlist mode)",
        default=env_values.get("ALLOWED_SENDERS") or "",
        required=env_values["SENDER_POLICY_MODE"] == "allowlist",
    )

    write_env_file(env_path, env_values)
    print(f"Saved {env_path}")
    return env_values


def configure_cx_providers(env_path: Path, env_values: dict[str, str]) -> dict[str, str]:
    print_header("Dispensary CX Providers")
    print("Configure the store knowledge base and order lookup source used by the email agent.")

    env_values["KNOWLEDGE_PROVIDER"] = prompt_knowledge_provider(env_values.get("KNOWLEDGE_PROVIDER") or "manual")
    env_values["STORE_KNOWLEDGE_FILE"] = prompt(
        "Store knowledge JSON path",
        default=env_values.get("STORE_KNOWLEDGE_FILE") or "./examples/store_knowledge.sample.json",
        required=True,
    )

    env_values["ORDER_PROVIDER"] = prompt_order_provider(env_values.get("ORDER_PROVIDER") or "manual")
    if env_values["ORDER_PROVIDER"] == "manual":
        env_values["MANUAL_ORDER_FILE"] = prompt(
            "Manual orders JSON path",
            default=env_values.get("MANUAL_ORDER_FILE") or "./examples/manual_orders.sample.json",
            required=True,
        )
    elif env_values["ORDER_PROVIDER"] == "dutchie":
        env_values["DUTCHIE_LOCATION_KEY"] = prompt(
            "Dutchie location key",
            default=env_values.get("DUTCHIE_LOCATION_KEY") or env_values.get("DUTCHIE_API_KEY") or None,
            secret=True,
            required=True,
        )
        env_values["DUTCHIE_INTEGRATOR_KEY"] = prompt(
            "Dutchie integrator key (optional)",
            default=env_values.get("DUTCHIE_INTEGRATOR_KEY") or None,
            secret=True,
        )
        env_values["DUTCHIE_API_BASE_URL"] = prompt(
            "Dutchie API base URL",
            default=env_values.get("DUTCHIE_API_BASE_URL") or "https://api.pos.dutchie.com",
            required=True,
        )
    elif env_values["ORDER_PROVIDER"] == "treez":
        env_values["TREEZ_DISPENSARY"] = prompt(
            "Treez dispensary slug or name",
            default=env_values.get("TREEZ_DISPENSARY") or None,
            required=True,
        )
        env_values["TREEZ_ORGANIZATION_ID"] = prompt(
            "Treez organization ID",
            default=env_values.get("TREEZ_ORGANIZATION_ID") or None,
            required=True,
        )
        env_values["TREEZ_CERTIFICATE_ID"] = prompt(
            "Treez certificate ID",
            default=env_values.get("TREEZ_CERTIFICATE_ID") or None,
            required=True,
        )
        env_values["TREEZ_PRIVATE_KEY_FILE"] = prompt(
            "Treez private key PEM path",
            default=env_values.get("TREEZ_PRIVATE_KEY_FILE") or None,
            required=True,
        )
        env_values["TREEZ_API_BASE_URL"] = prompt(
            "Treez API base URL",
            default=env_values.get("TREEZ_API_BASE_URL") or "https://api-prod.treez.io",
            required=True,
        )
    elif env_values["ORDER_PROVIDER"] == "jane":
        env_values["JANE_BRIDGE_URL"] = prompt(
            "Jane bridge URL",
            default=env_values.get("JANE_BRIDGE_URL") or None,
            required=True,
        )
        env_values["JANE_BRIDGE_TOKEN"] = prompt(
            "Jane bridge bearer token (optional)",
            default=env_values.get("JANE_BRIDGE_TOKEN") or None,
            secret=True,
        )
        env_values["JANE_BRIDGE_TIMEOUT_SECONDS"] = prompt(
            "Jane bridge timeout seconds",
            default=env_values.get("JANE_BRIDGE_TIMEOUT_SECONDS") or env_values.get("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS") or "15",
            required=True,
        )
    elif env_values["ORDER_PROVIDER"] == "bridge":
        env_values["BRIDGE_ORDER_PROVIDER_URL"] = prompt(
            "Bridge order provider URL",
            default=env_values.get("BRIDGE_ORDER_PROVIDER_URL") or None,
            required=True,
        )
        env_values["BRIDGE_ORDER_PROVIDER_TOKEN"] = prompt(
            "Bridge order provider bearer token (optional)",
            default=env_values.get("BRIDGE_ORDER_PROVIDER_TOKEN") or None,
            secret=True,
        )
        env_values["BRIDGE_ORDER_PROVIDER_SOURCE"] = prompt(
            "Bridge provider source label",
            default=env_values.get("BRIDGE_ORDER_PROVIDER_SOURCE") or "bridge",
            required=True,
        )
        env_values["BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS"] = prompt(
            "Bridge timeout seconds",
            default=env_values.get("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS") or "15",
            required=True,
        )
    else:
        env_values["ORDER_PROVIDER_FACTORY"] = prompt(
            "Custom order provider factory (module:attribute)",
            default=env_values.get("ORDER_PROVIDER_FACTORY") or None,
            required=True,
        )

    write_env_file(env_path, env_values)
    print(f"Saved {env_path}")
    return env_values


def configure_gog_connection_env(env_path: Path, env_values: dict[str, str]) -> dict[str, str]:
    print_header("gog Gmail Runtime")
    print("This flow keeps setup inside Mailroom, but it will still launch `gog` and `gcloud` when needed.")
    print("Important: gog Gmail watch uses Gmail Pub/Sub, so this deployment still needs one GCP project you control.")
    print("Your end users do not need their own Google Cloud setup, but the Mailroom deployment does.")
    print("You also need a public HTTPS push endpoint for Gmail Pub/Sub to reach your local watcher.")

    env_values["GOG_ACCOUNT"] = prompt_email(
        "gog account email",
        default=env_values.get("GOG_ACCOUNT") or env_values.get("AGENT_EMAIL") or None,
        required=True,
    )

    topic_parts = parse_gcp_topic(env_values.get("GOG_GMAIL_TOPIC"))
    project_id_default = topic_parts[0] if topic_parts else (detect_gcloud_project() or "")
    topic_name_default = topic_parts[1] if topic_parts else "gog-gmail-watch"

    full_topic_default = env_values.get("GOG_GMAIL_TOPIC") or ""
    full_topic = prompt(
        "Existing Pub/Sub topic (projects/<project-id>/topics/<topic-name>)",
        default=full_topic_default or None,
    ).strip()
    parsed_full_topic = parse_gcp_topic(full_topic)
    if parsed_full_topic:
        env_values["GOG_GMAIL_TOPIC"] = full_topic
    else:
        if full_topic:
            print("That topic format is invalid. Falling back to project id + topic name.")
        project_id = prompt(
            "GCP project id for Gmail Pub/Sub",
            default=project_id_default or None,
            required=True,
        )
        topic_name = prompt("Pub/Sub topic name", default=topic_name_default, required=True)
        env_values["GOG_GMAIL_TOPIC"] = f"projects/{project_id}/topics/{topic_name}"

    env_values["GOG_GMAIL_LABEL"] = prompt(
        "Gmail label to watch",
        default=env_values.get("GOG_GMAIL_LABEL") or "INBOX",
        required=True,
    )
    env_values["GOG_GMAIL_HOOK_URL"] = prompt(
        "Local hook URL",
        default=env_values.get("GOG_GMAIL_HOOK_URL") or "http://127.0.0.1:8787/hooks/gmail",
        required=True,
    )
    env_values["GOG_GMAIL_HOOK_TOKEN"] = prompt(
        "Hook token",
        default=env_values.get("GOG_GMAIL_HOOK_TOKEN") or secrets.token_hex(24),
        required=True,
    )
    env_values["GOG_GMAIL_PUSH_TOKEN"] = prompt(
        "Push token",
        default=env_values.get("GOG_GMAIL_PUSH_TOKEN") or secrets.token_hex(24),
        required=True,
    )
    env_values["GOG_GMAIL_SERVE_BIND"] = prompt(
        "gog watch serve bind host",
        default=env_values.get("GOG_GMAIL_SERVE_BIND") or "127.0.0.1",
        required=True,
    )
    env_values["GOG_GMAIL_SERVE_PORT"] = prompt(
        "gog watch serve port",
        default=env_values.get("GOG_GMAIL_SERVE_PORT") or "8788",
        required=True,
    )
    env_values["GOG_GMAIL_SERVE_PATH"] = prompt(
        "gog watch serve path",
        default=env_values.get("GOG_GMAIL_SERVE_PATH") or "/gmail-pubsub",
        required=True,
    )
    env_values["GOG_GMAIL_INCLUDE_BODY"] = prompt(
        "Include email body snippets (true/false)",
        default=env_values.get("GOG_GMAIL_INCLUDE_BODY") or "true",
        required=True,
    )
    env_values["GOG_GMAIL_MAX_BYTES"] = prompt(
        "Max body snippet bytes",
        default=env_values.get("GOG_GMAIL_MAX_BYTES") or "20000",
        required=True,
    )
    env_values["GOG_GMAIL_RENEW_EVERY_MINUTES"] = prompt(
        "Renew watch every N minutes",
        default=env_values.get("GOG_GMAIL_RENEW_EVERY_MINUTES") or "720",
        required=True,
    )
    env_values["GOG_GMAIL_SUBSCRIPTION"] = prompt(
        "Pub/Sub subscription name",
        default=env_values.get("GOG_GMAIL_SUBSCRIPTION") or "gog-gmail-watch-push",
        required=True,
    )
    env_values["GOG_GMAIL_PUSH_ENDPOINT"] = prompt(
        "Public HTTPS push endpoint URL",
        default=env_values.get("GOG_GMAIL_PUSH_ENDPOINT") or "",
    )

    write_env_file(env_path, env_values)
    print(f"Saved {env_path}")
    return env_values


def run_gog_connection_actions(env_values: dict[str, str]) -> int:
    print_header("gog Connection Actions")

    if not command_exists("gog"):
        print("`gog` is not installed on this machine. Install it, then rerun `mailroom connections`.")
    else:
        if confirm("Run `gog auth credentials` now?", default=False):
            client_secret_path = prompt("Path to gog OAuth client JSON", required=True)
            exit_code = run_logged_subprocess(["gog", "auth", "credentials", client_secret_path])
            if exit_code != 0:
                print("`gog auth credentials` did not complete successfully.")
        if confirm("Run `gog auth add` now for the agent mailbox?", default=True):
            services = prompt("gog services", default="gmail", required=True)
            exit_code = run_logged_subprocess(
                ["gog", "auth", "add", env_values["GOG_ACCOUNT"], "--services", services]
            )
            if exit_code != 0:
                print("`gog auth add` did not complete successfully.")
        if confirm("Show `gog auth list` now?", default=True):
            run_logged_subprocess(["gog", "auth", "list"])

    if not command_exists("gcloud"):
        print("`gcloud` is not installed on this machine. Install it before running the Gmail watch setup.")
    else:
        if confirm("Run `gcloud auth login` now?", default=False):
            run_logged_subprocess(["gcloud", "auth", "login"])

        parsed_topic = parse_gcp_topic(env_values.get("GOG_GMAIL_TOPIC"))
        if parsed_topic and confirm("Run Gmail Pub/Sub setup now?", default=True):
            project_id, topic_name = parsed_topic
            run_logged_subprocess(["gcloud", "config", "set", "project", project_id])
            run_logged_subprocess(
                [
                    "gcloud",
                    "services",
                    "enable",
                    "gmail.googleapis.com",
                    "pubsub.googleapis.com",
                    "--project",
                    project_id,
                ]
            )
            run_logged_subprocess(["gcloud", "pubsub", "topics", "create", topic_name, "--project", project_id])
            run_logged_subprocess(
                [
                    "gcloud",
                    "pubsub",
                    "topics",
                    "add-iam-policy-binding",
                    topic_name,
                    "--project",
                    project_id,
                    "--member",
                    "serviceAccount:gmail-api-push@system.gserviceaccount.com",
                    "--role",
                    "roles/pubsub.publisher",
                ]
            )
            push_endpoint = env_values.get("GOG_GMAIL_PUSH_ENDPOINT", "").strip()
            if push_endpoint:
                run_logged_subprocess(
                    [
                        "gcloud",
                        "pubsub",
                        "subscriptions",
                        "create",
                        env_values["GOG_GMAIL_SUBSCRIPTION"],
                        "--project",
                        project_id,
                        "--topic",
                        topic_name,
                        "--push-endpoint",
                        push_endpoint,
                    ]
                )
            else:
                print("Skipping Pub/Sub subscription creation because `GOG_GMAIL_PUSH_ENDPOINT` is blank.")

    print_header("Setup Complete")
    print("Next commands:")
    print("1. mailroom doctor")
    print("2. mailroom run --reload")
    print("3. curl http://127.0.0.1:8787/healthz")
    print()
    print("Notes:")
    print("- gog mode skips credentials.json and token.json")
    print("- If Gmail does not reach your local watcher, verify the public push endpoint and Pub/Sub subscription.")
    return 0


def complete_gog_setup(env_path: Path, env_values: dict[str, str]) -> int:
    configure_gog_connection_env(env_path, env_values)
    return run_gog_connection_actions(env_values)


def doctor_command(_: argparse.Namespace) -> int:
    env_values = parse_env_file(REPO_ROOT / ".env")
    mail_provider = normalize_mail_provider(env_values.get("MAIL_PROVIDER"))
    order_provider = normalize_order_provider(env_values.get("ORDER_PROVIDER"))
    knowledge_provider = normalize_knowledge_provider(env_values.get("KNOWLEDGE_PROVIDER"))
    credentials_path = resolve_runtime_path(env_values.get("GOOGLE_CREDENTIALS_FILE"), "./credentials.json")
    token_path = resolve_runtime_path(env_values.get("GOOGLE_TOKEN_FILE"), "./token.json")
    store_knowledge_path = resolve_runtime_path(
        env_values.get("STORE_KNOWLEDGE_FILE"),
        "./examples/store_knowledge.sample.json",
    )
    manual_order_path = resolve_runtime_path(
        env_values.get("MANUAL_ORDER_FILE"),
        "./examples/manual_orders.sample.json",
    )
    treez_private_key_path = resolve_runtime_path(
        env_values.get("TREEZ_PRIVATE_KEY_FILE"),
        "./treez-private-key.pem",
    )
    prompt_path = resolve_runtime_path(env_values.get("SYSTEM_PROMPT_FILE"), "./SYSTEM_PROMPT.md")
    state_path = resolve_runtime_path(env_values.get("STATE_DB"), "./state.db")

    checks: list[tuple[bool, str, str]] = [
        (sys.version_info >= (3, 11), "python", f"Python {sys.version.split()[0]}"),
        ((REPO_ROOT / ".env.example").exists(), "env example", str(REPO_ROOT / ".env.example")),
        ((REPO_ROOT / ".env").exists(), "env file", str(REPO_ROOT / ".env")),
        (bool(env_values.get("OPENAI_API_KEY")), "OPENAI_API_KEY", "set in .env"),
        (bool(env_values.get("AGENT_EMAIL")), "AGENT_EMAIL", env_values.get("AGENT_EMAIL", "missing")),
        (mail_provider in {"google_api", "gog"}, "MAIL_PROVIDER", mail_provider),
        (order_provider in {"manual", "dutchie", "treez", "jane", "bridge", "custom"}, "ORDER_PROVIDER", order_provider),
        (knowledge_provider == "manual", "KNOWLEDGE_PROVIDER", knowledge_provider),
        (store_knowledge_path.exists(), "STORE_KNOWLEDGE_FILE", str(store_knowledge_path)),
        (
            normalize_sender_policy_mode(env_values.get("SENDER_POLICY_MODE")) in {"all", "allowlist"},
            "SENDER_POLICY_MODE",
            normalize_sender_policy_mode(env_values.get("SENDER_POLICY_MODE")),
        ),
        (prompt_path.exists(), "system prompt", str(prompt_path)),
        (importlib.util.find_spec("openai") is not None, "python dependency", "openai installed"),
        (importlib.util.find_spec("fastapi") is not None, "python dependency", "fastapi installed"),
        (importlib.util.find_spec("uvicorn") is not None, "python dependency", "uvicorn installed"),
    ]

    sender_policy_mode = normalize_sender_policy_mode(env_values.get("SENDER_POLICY_MODE"))
    if sender_policy_mode == "allowlist":
        checks.append(
            (
                bool(env_values.get("ALLOWED_SENDERS", "").strip()),
                "ALLOWED_SENDERS",
                env_values.get("ALLOWED_SENDERS", "missing"),
            )
        )

    if order_provider == "manual":
        checks.append((manual_order_path.exists(), "MANUAL_ORDER_FILE", str(manual_order_path)))
    elif order_provider == "dutchie":
        checks.extend(
            [
                (
                    bool(env_values.get("DUTCHIE_LOCATION_KEY") or env_values.get("DUTCHIE_API_KEY")),
                    "DUTCHIE_LOCATION_KEY",
                    "set in .env",
                ),
                (
                    bool(env_values.get("DUTCHIE_API_BASE_URL", "").strip()),
                    "DUTCHIE_API_BASE_URL",
                    env_values.get("DUTCHIE_API_BASE_URL", "missing"),
                ),
            ]
        )
    elif order_provider == "treez":
        checks.extend(
            [
                (bool(env_values.get("TREEZ_DISPENSARY", "").strip()), "TREEZ_DISPENSARY", env_values.get("TREEZ_DISPENSARY", "missing")),
                (
                    bool(env_values.get("TREEZ_ORGANIZATION_ID", "").strip()),
                    "TREEZ_ORGANIZATION_ID",
                    env_values.get("TREEZ_ORGANIZATION_ID", "missing"),
                ),
                (
                    bool(env_values.get("TREEZ_CERTIFICATE_ID", "").strip()),
                    "TREEZ_CERTIFICATE_ID",
                    env_values.get("TREEZ_CERTIFICATE_ID", "missing"),
                ),
                (treez_private_key_path.exists(), "TREEZ_PRIVATE_KEY_FILE", str(treez_private_key_path)),
                (
                    bool(env_values.get("TREEZ_API_BASE_URL", "").strip()),
                    "TREEZ_API_BASE_URL",
                    env_values.get("TREEZ_API_BASE_URL", "missing"),
                ),
            ]
        )
    elif order_provider == "jane":
        checks.extend(
            [
                (bool(env_values.get("JANE_BRIDGE_URL", "").strip()), "JANE_BRIDGE_URL", env_values.get("JANE_BRIDGE_URL", "missing")),
                (
                    bool(env_values.get("JANE_BRIDGE_TIMEOUT_SECONDS", "").strip() or env_values.get("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS", "").strip()),
                    "JANE_BRIDGE_TIMEOUT_SECONDS",
                    env_values.get("JANE_BRIDGE_TIMEOUT_SECONDS") or env_values.get("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS") or "missing",
                ),
            ]
        )
    elif order_provider == "bridge":
        checks.extend(
            [
                (
                    bool(env_values.get("BRIDGE_ORDER_PROVIDER_URL", "").strip()),
                    "BRIDGE_ORDER_PROVIDER_URL",
                    env_values.get("BRIDGE_ORDER_PROVIDER_URL", "missing"),
                ),
                (
                    bool(env_values.get("BRIDGE_ORDER_PROVIDER_SOURCE", "").strip()),
                    "BRIDGE_ORDER_PROVIDER_SOURCE",
                    env_values.get("BRIDGE_ORDER_PROVIDER_SOURCE", "missing"),
                ),
                (
                    bool(env_values.get("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS", "").strip()),
                    "BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS",
                    env_values.get("BRIDGE_ORDER_PROVIDER_TIMEOUT_SECONDS", "missing"),
                ),
            ]
        )
    else:
        custom_factory_ok, custom_factory_detail = validate_import_path(env_values.get("ORDER_PROVIDER_FACTORY"))
        checks.append((custom_factory_ok, "ORDER_PROVIDER_FACTORY", custom_factory_detail))

    if mail_provider == "google_api":
        checks.extend(
            [
                (credentials_path.exists(), "credentials file", str(credentials_path)),
                (token_path.exists(), "token file", str(token_path)),
            ]
        )
        credentials_ok, credentials_detail = validate_desktop_oauth_client(credentials_path)
        if credentials_path.exists():
            checks.append((credentials_ok, "credentials format", credentials_detail))
    else:
        checks.extend(
            [
                (bool(env_values.get("GOG_GMAIL_TOPIC")), "GOG_GMAIL_TOPIC", env_values.get("GOG_GMAIL_TOPIC", "missing")),
                (bool(env_values.get("GOG_GMAIL_SUBSCRIPTION")), "GOG_GMAIL_SUBSCRIPTION", env_values.get("GOG_GMAIL_SUBSCRIPTION", "missing")),
                (bool(env_values.get("GOG_GMAIL_PUSH_ENDPOINT")), "GOG_GMAIL_PUSH_ENDPOINT", env_values.get("GOG_GMAIL_PUSH_ENDPOINT", "missing")),
                (bool(env_values.get("GOG_GMAIL_HOOK_TOKEN")), "GOG_GMAIL_HOOK_TOKEN", "set in .env"),
                (bool(env_values.get("GOG_GMAIL_PUSH_TOKEN")), "GOG_GMAIL_PUSH_TOKEN", "set in .env"),
                (command_exists("gog"), "gog binary", "gog available on PATH"),
            ]
        )

    optional_checks = [
        (command_exists("gcloud"), "optional command", "gcloud available"),
        (command_exists("sqlite3"), "optional command", "sqlite3 available"),
    ]
    if mail_provider == "google_api":
        optional_checks.insert(0, (command_exists("gws"), "optional command", "gws available"))

    print_header("Mailroom Doctor")
    print(f"Repo root: {REPO_ROOT}")
    print(f"State DB path: {state_path}")
    print(f"Mail provider: {mail_provider}")
    print(f"Order provider: {order_provider}")
    print(f"Knowledge provider: {knowledge_provider}")
    print()

    failed = False
    for ok, label, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {label}: {detail}")
        failed = failed or not ok

    for ok, label, detail in optional_checks:
        status = "OK" if ok else "WARN"
        print(f"[{status}] {label}: {detail}")

    if failed:
        print()
        print("Doctor found blocking issues. Run `mailroom setup` to fix the common ones.")
        return 1

    print()
    print("Doctor checks passed.")
    return 0


def auth_command(_: argparse.Namespace) -> int:
    env_values = parse_env_file(REPO_ROOT / ".env")
    mail_provider = normalize_mail_provider(env_values.get("MAIL_PROVIDER"))
    if mail_provider != "google_api":
        print("mailroom auth is only used for MAIL_PROVIDER=google_api.")
        return 0
    credentials_path = resolve_runtime_path(env_values.get("GOOGLE_CREDENTIALS_FILE"), "./credentials.json")
    ok, detail = validate_desktop_oauth_client(credentials_path)
    if not ok:
        print(detail)
        print("Run `mailroom setup` to walk through the Google auth prerequisites.")
        return 1
    return run_google_auth()


def access_command(_: argparse.Namespace) -> int:
    env_path, env_values = ensure_env_file()

    if not env_values.get("AGENT_EMAIL"):
        print_header("Mailbox")
        env_values["AGENT_EMAIL"] = prompt_email("Agent Gmail address", required=True)
        write_env_file(env_path, env_values)
        print(f"Saved {env_path}")

    configure_sender_policy(env_path, env_values)

    print_header("Access Updated")
    print("Next commands:")
    print("1. mailroom doctor")
    print("2. restart the app if it is already running")
    print("3. curl http://127.0.0.1:8787/healthz")
    return 0


def run_command(args: argparse.Namespace) -> int:
    os.chdir(REPO_ROOT)
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def wait_for_credentials_file(credentials_path: Path):
    while True:
        ok, detail = validate_desktop_oauth_client(credentials_path)
        if ok:
            print(detail)
            return

        print()
        print("The app still needs a Google desktop OAuth client JSON file.")
        print(f"Expected location: {credentials_path}")
        print()
        print("Do this in Google Cloud Console:")
        print("1. Enable Gmail API.")
        print("2. Configure the OAuth branding and audience screens.")
        print("3. Create an OAuth client with Application type = Desktop app.")
        print("4. Download the JSON and save it as the credentials file above.")
        print()
        print("Helpful links:")
        for name, url in GOOGLE_SETUP_URLS.items():
            print(f"- {name}: {url}")
        print()
        if command_exists("gws"):
            print("Optional helper: `gws auth setup` can help with Google Cloud project setup,")
            print("but this app still needs the downloaded desktop OAuth JSON file.")
            print()

        action = input(
            "Type `open` to open the links, `gws` to run `gws auth setup`, "
            "`retry` to re-check the file, or `quit` to stop: "
        ).strip().lower()

        if action == "open":
            open_google_setup_urls()
            continue
        if action == "gws":
            if not command_exists("gws"):
                print("`gws` is not installed on this machine.")
                continue
            run_subprocess(["gws", "auth", "setup"], cwd=REPO_ROOT)
            continue
        if action in {"retry", ""}:
            continue
        if action in {"quit", "q", "exit"}:
            raise SystemExit(1)


def setup_command(_: argparse.Namespace) -> int:
    print_header("Mailroom Setup")
    print(
        textwrap.dedent(
            """
            This wizard prepares the local Canna Mailroom runtime.

            It will:
            - create or update `.env`
            - collect the base Mailroom runtime settings
            - configure dispensary CX providers
            - hand off to the selected email connection wizard
            - show next steps to launch and test the app
            """
        ).strip()
    )

    env_path, env_values = ensure_env_file()

    print_header("Environment")
    env_values["OPENAI_API_KEY"] = prompt(
        "OpenAI API key",
        default=env_values.get("OPENAI_API_KEY") or None,
        secret=True,
        required=True,
    )
    env_values["MAIL_PROVIDER"] = prompt_mail_provider(env_values.get("MAIL_PROVIDER"))
    env_values["AGENT_EMAIL"] = prompt_email(
        "Agent Gmail address",
        default=env_values.get("AGENT_EMAIL") or None,
        required=True,
    )
    configure_sender_policy(env_path, env_values)
    env_values["OPENAI_MODEL"] = prompt(
        "OpenAI model",
        default=env_values.get("OPENAI_MODEL") or "gpt-5.4",
        required=True,
    )
    env_values["POLL_SECONDS"] = prompt(
        "Poll interval in seconds",
        default=env_values.get("POLL_SECONDS") or "20",
        required=True,
    )
    configure_cx_providers(env_path, env_values)

    write_env_file(env_path, env_values)
    print(f"Saved {env_path}")

    if normalize_mail_provider(env_values["MAIL_PROVIDER"]) == "gog":
        return complete_gog_setup(env_path, env_values)
    return complete_google_api_setup(env_values)


def connections_command(_: argparse.Namespace) -> int:
    env_path, env_values = ensure_env_file()

    print_header("Mailroom Connections")
    current_provider = normalize_mail_provider(env_values.get("MAIL_PROVIDER"))
    provider = prompt_mail_provider(current_provider or "google_api")
    env_values["MAIL_PROVIDER"] = provider
    write_env_file(env_path, env_values)
    print(f"Saved {env_path}")

    if not env_values.get("AGENT_EMAIL"):
        print_header("Mailbox")
        env_values["AGENT_EMAIL"] = prompt_email("Agent Gmail address", required=True)
        write_env_file(env_path, env_values)
        print(f"Saved {env_path}")

    print(f"Provider: {provider}")

    if provider == "gog":
        return complete_gog_setup(env_path, env_values)
    return complete_google_api_setup(env_values)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mailroom", description="Canna Mailroom local CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="interactive local setup wizard")
    setup_parser.set_defaults(func=setup_command)

    connections_parser = subparsers.add_parser(
        "connections", help="interactive email connection wizard"
    )
    connections_parser.set_defaults(func=connections_command)

    doctor_parser = subparsers.add_parser("doctor", help="check config, auth files, and dependencies")
    doctor_parser.set_defaults(func=doctor_command)

    auth_parser = subparsers.add_parser("auth", help="run the Google OAuth browser flow")
    auth_parser.set_defaults(func=auth_command)

    access_parser = subparsers.add_parser("access", help="interactive sender access policy wizard")
    access_parser.set_defaults(func=access_command)

    run_parser = subparsers.add_parser("run", help="start the FastAPI app")
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", type=int, default=8787)
    run_parser.add_argument("--reload", action="store_true")
    run_parser.set_defaults(func=run_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
