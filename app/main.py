from __future__ import annotations

import threading
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException

from app.settings import settings
from app.google_clients import get_credentials, get_gmail_service
from app.gog_mailbox import GogMailboxProvider
from app.gog_watcher import GogGmailWatcherManager, GogWatcherConfig
from app.google_mailbox import GoogleApiMailboxProvider
from app.ai_agent import EmailAgent
from app.cx_providers import load_knowledge_provider, load_order_provider
from app.cx_toolset import DispensaryCxToolset
from app.mailbox import MailboxMessage
from app.state import StateStore
from app.gmail_worker import EmailThreadWorker

app = FastAPI(title="Canna Mailroom", version="0.1.0")

worker_thread: threading.Thread | None = None
worker: EmailThreadWorker | None = None
watcher: GogGmailWatcherManager | None = None


def _build_hook_messages(payload: dict) -> list[MailboxMessage]:
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        return []

    messages: list[MailboxMessage] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        message_id = str(item.get("id") or item.get("message_id") or item.get("messageId") or "").strip()
        if not message_id:
            continue
        thread_id = str(item.get("threadId") or item.get("thread_id") or message_id).strip() or message_id
        body_text = str(item.get("body") or item.get("snippet") or "").strip()
        message_id_header = item.get("messageIdHeader") or item.get("message_id_header") or item.get("rfc822MessageId")
        messages.append(
            MailboxMessage(
                message_id=message_id,
                thread_id=thread_id,
                from_header=str(item.get("from") or ""),
                subject=str(item.get("subject") or "(no subject)"),
                message_id_header=str(message_id_header).strip() if message_id_header else None,
                body_text=body_text,
            )
        )
    return messages


def _validate_hook_token(authorization: str | None, x_mailroom_token: str | None) -> None:
    expected = settings.gog_gmail_hook_token.strip()
    if not expected:
        raise HTTPException(status_code=500, detail="GOG_GMAIL_HOOK_TOKEN is not configured")

    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()

    candidate = bearer or (x_mailroom_token or "").strip()
    if candidate != expected:
        raise HTTPException(status_code=401, detail="invalid hook token")


@app.on_event("startup")
def startup():
    global watcher, worker_thread, worker
    state = StateStore(settings.state_db)
    order_provider = load_order_provider(settings)
    knowledge_provider = load_knowledge_provider(settings)
    toolset = DispensaryCxToolset(order_provider=order_provider, knowledge_provider=knowledge_provider)

    if settings.mail_provider == "google_api":
        creds = get_credentials(settings.google_token_file, settings.google_credentials_file)
        gmail = get_gmail_service(creds)
        mailbox = GoogleApiMailboxProvider(gmail_service=gmail)
    elif settings.mail_provider == "gog":
        mailbox = GogMailboxProvider(account=settings.gog_account or settings.agent_email)
        watcher = GogGmailWatcherManager(
            GogWatcherConfig(
                account=settings.gog_account or settings.agent_email,
                topic=settings.gog_gmail_topic,
                label=settings.gog_gmail_label,
                hook_url=settings.gog_gmail_hook_url,
                hook_token=settings.gog_gmail_hook_token,
                push_token=settings.gog_gmail_push_token,
                serve_bind=settings.gog_gmail_serve_bind,
                serve_port=settings.gog_gmail_serve_port,
                serve_path=settings.gog_gmail_serve_path,
                include_body=settings.gog_gmail_include_body,
                max_bytes=settings.gog_gmail_max_bytes,
                renew_every_minutes=settings.gog_gmail_renew_every_minutes,
            )
        )
        watcher.start()
    else:
        raise RuntimeError(f"Unsupported MAIL_PROVIDER: {settings.mail_provider}")

    agent = EmailAgent(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        toolset=toolset,
        system_prompt_path=settings.system_prompt_file,
    )

    worker = EmailThreadWorker(
        mailbox=mailbox,
        agent_email=settings.agent_email,
        state=state,
        agent=agent,
        sender_policy_mode=settings.sender_policy_mode,
        allowed_senders=settings.allowed_senders,
        retry_max_attempts=settings.retry_max_attempts,
        retry_base_delay_ms=settings.retry_base_delay_ms,
        retry_max_delay_ms=settings.retry_max_delay_ms,
        retry_jitter_ms=settings.retry_jitter_ms,
    )

    if settings.mail_provider == "google_api":
        worker_thread = threading.Thread(
            target=worker.run_forever,
            kwargs={"poll_seconds": settings.poll_seconds},
            daemon=True,
        )
        worker_thread.start()
    else:
        worker_thread = None


@app.on_event("shutdown")
def shutdown():
    global watcher
    if watcher:
        watcher.stop()
        watcher = None


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "agent_email": settings.agent_email,
        "mail_provider": settings.mail_provider,
        "sender_policy_mode": settings.sender_policy_mode,
        "allowed_senders_count": len(settings.allowed_senders),
        "ingress_mode": "poll" if settings.mail_provider == "google_api" else "hook",
        "order_provider": settings.order_provider,
        "knowledge_provider": settings.knowledge_provider,
        "poll_seconds": settings.poll_seconds,
        "worker_alive": bool(worker_thread and worker_thread.is_alive()) or settings.mail_provider == "gog",
        "watcher_alive": watcher.is_running() if watcher else None,
        "retry": {
            "max_attempts": settings.retry_max_attempts,
            "base_delay_ms": settings.retry_base_delay_ms,
            "max_delay_ms": settings.retry_max_delay_ms,
            "jitter_ms": settings.retry_jitter_ms,
        },
    }


@app.post("/process-now")
def process_now():
    if not worker:
        return {"ok": False, "error": "worker not initialized"}
    if settings.mail_provider != "google_api":
        return {"ok": False, "error": "process-now is only supported in polling mode"}
    count = worker.process_once()
    return {"ok": True, "processed": count}


@app.get("/dead-letter")
def dead_letter(limit: int = 50):
    if not worker:
        return {"ok": False, "error": "worker not initialized"}
    clamped = max(1, min(limit, 200))
    items = worker.state.list_dead_letters(limit=clamped)
    return {"ok": True, "count": len(items), "items": items}


@app.post("/dead-letter/requeue/{message_id}")
def dead_letter_requeue(message_id: str, process_now: bool = True):
    if not worker:
        return {"ok": False, "error": "worker not initialized"}
    processed = worker.requeue_dead_letter(message_id, process_immediately=process_now)
    return {"ok": True, "requeued": message_id, "processed_now": processed}


@app.post("/hooks/gmail", status_code=202)
def gmail_hook(
    payload: dict,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    x_mailroom_token: str | None = Header(default=None),
):
    if settings.mail_provider != "gog":
        raise HTTPException(status_code=400, detail="gmail hook is only enabled in gog mode")
    if not worker:
        raise HTTPException(status_code=500, detail="worker not initialized")

    _validate_hook_token(authorization, x_mailroom_token)
    messages = _build_hook_messages(payload)
    if not messages:
        raise HTTPException(status_code=400, detail="payload did not contain any usable messages")

    for message in messages:
        background_tasks.add_task(worker.process_mailbox_message, message)

    return {"ok": True, "queued": len(messages)}
