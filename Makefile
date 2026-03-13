PYTHON ?= python3.11

.PHONY: setup wizard connections access auth doctor run

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip setuptools wheel
	. .venv/bin/activate && pip install -e .

wizard:
	. .venv/bin/activate && mailroom setup

connections:
	. .venv/bin/activate && mailroom connections

access:
	. .venv/bin/activate && mailroom access

auth:
	. .venv/bin/activate && mailroom auth

doctor:
	. .venv/bin/activate && mailroom doctor

run:
	. .venv/bin/activate && mailroom run --reload
