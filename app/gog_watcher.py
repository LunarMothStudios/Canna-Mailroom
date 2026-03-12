from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
import threading
import time


@dataclass(frozen=True)
class GogWatcherConfig:
    account: str
    topic: str
    label: str
    hook_url: str
    hook_token: str
    push_token: str
    serve_bind: str
    serve_port: int
    serve_path: str
    include_body: bool
    max_bytes: int
    renew_every_minutes: int

    def validate(self) -> None:
        missing = []
        for name, value in {
            "account": self.account,
            "topic": self.topic,
            "hook_url": self.hook_url,
            "hook_token": self.hook_token,
            "push_token": self.push_token,
            "serve_bind": self.serve_bind,
            "serve_path": self.serve_path,
        }.items():
            if not str(value).strip():
                missing.append(name)
        if missing:
            raise RuntimeError(f"Missing gog watcher config: {', '.join(missing)}")
        if self.serve_port <= 0:
            raise RuntimeError("GOG_GMAIL_SERVE_PORT must be greater than 0")
        if self.renew_every_minutes <= 0:
            raise RuntimeError("GOG_GMAIL_RENEW_EVERY_MINUTES must be greater than 0")

    def watch_start_args(self) -> list[str]:
        return [
            "gmail",
            "watch",
            "start",
            "--account",
            self.account,
            "--label",
            self.label,
            "--topic",
            self.topic,
        ]

    def watch_serve_args(self) -> list[str]:
        args = [
            "gmail",
            "watch",
            "serve",
            "--account",
            self.account,
            "--bind",
            self.serve_bind,
            "--port",
            str(self.serve_port),
            "--path",
            self.serve_path,
            "--token",
            self.push_token,
            "--hook-url",
            self.hook_url,
            "--hook-token",
            self.hook_token,
        ]
        if self.include_body:
            args.append("--include-body")
        if self.max_bytes > 0:
            args.extend(["--max-bytes", str(self.max_bytes)])
        return args


class GogGmailWatcherManager:
    def __init__(self, config: GogWatcherConfig):
        self.config = config
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._child: subprocess.Popen[str] | None = None
        self._renew_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None

    def start(self) -> None:
        if shutil.which("gog") is None:
            raise RuntimeError("gog binary not found on PATH")

        self.config.validate()
        self._run_watch_start(fatal=True)
        self._spawn_serve()

        self._renew_thread = threading.Thread(target=self._renew_loop, daemon=True)
        self._renew_thread.start()

        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            child = self._child
            self._child = None

        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()

    def is_running(self) -> bool:
        with self._lock:
            child = self._child
            return child is not None and child.poll() is None

    def _run_watch_start(self, fatal: bool) -> None:
        command = ["gog", *self.config.watch_start_args()]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return

        error = (result.stderr or result.stdout or "gog gmail watch start failed").strip()
        if fatal:
            raise RuntimeError(error)
        print(f"Watcher renew failed: {error}")

    def _spawn_serve(self) -> None:
        command = ["gog", *self.config.watch_serve_args()]
        child = subprocess.Popen(command)
        with self._lock:
            self._child = child

    def _renew_loop(self) -> None:
        sleep_seconds = max(60, self.config.renew_every_minutes * 60)
        while not self._stop_event.wait(sleep_seconds):
            try:
                self._run_watch_start(fatal=False)
            except Exception as err:
                print(f"Watcher renew error: {err.__class__.__name__}: {err}")

    def _monitor_loop(self) -> None:
        while not self._stop_event.wait(2):
            with self._lock:
                child = self._child

            if child is None:
                continue

            exit_code = child.poll()
            if exit_code is None:
                continue

            if self._stop_event.is_set():
                return

            print(f"gog gmail watch serve exited with code {exit_code}; restarting in 2s")
            time.sleep(2)
            if self._stop_event.is_set():
                return
            self._spawn_serve()
