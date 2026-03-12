from __future__ import annotations

import threading
from fastapi import FastAPI

from app.settings import settings
from app.google_clients import get_credentials, get_docs_service, get_drive_service, get_gmail_service
from app.tools import GoogleWorkspaceTools
from app.ai_agent import EmailAgent
from app.state import StateStore
from app.gmail_worker import GmailThreadWorker

app = FastAPI(title="Canna Mailroom", version="0.1.0")

worker_thread: threading.Thread | None = None
worker: GmailThreadWorker | None = None


@app.on_event("startup")
def startup():
    global worker_thread, worker

    creds = get_credentials(settings.google_token_file, settings.google_credentials_file)
    gmail = get_gmail_service(creds)
    drive = get_drive_service(creds)
    docs = get_docs_service(creds)

    state = StateStore(settings.state_db)
    tools = GoogleWorkspaceTools(drive=drive, docs=docs, default_folder_id=settings.google_drive_default_folder_id)

    agent = EmailAgent(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        tools=tools,
        system_prompt_path=settings.system_prompt_file,
    )

    worker = GmailThreadWorker(
        gmail_service=gmail,
        agent_email=settings.agent_email,
        state=state,
        agent=agent,
        retry_max_attempts=settings.retry_max_attempts,
        retry_base_delay_ms=settings.retry_base_delay_ms,
        retry_max_delay_ms=settings.retry_max_delay_ms,
        retry_jitter_ms=settings.retry_jitter_ms,
    )

    worker_thread = threading.Thread(target=worker.run_forever, kwargs={"poll_seconds": settings.poll_seconds}, daemon=True)
    worker_thread.start()


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "agent_email": settings.agent_email,
        "poll_seconds": settings.poll_seconds,
        "worker_alive": bool(worker_thread and worker_thread.is_alive()),
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
