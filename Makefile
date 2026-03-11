.PHONY: setup auth run

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -e .

auth:
	. .venv/bin/activate && python scripts/auth_google.py

run:
	. .venv/bin/activate && uvicorn app.main:app --reload --port 8787
