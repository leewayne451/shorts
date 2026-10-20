# whatif-shorts — convenience targets.
# `make` is optional and NOT needed on Windows; run `python -m whatif.run ...` directly.

PYTHON ?= python
SUBJECT ?=
DRY_RUN ?=

.PHONY: setup run run-topic test clean

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

run:
ifndef SUBJECT
	$(error SUBJECT is not set. Usage: make run SUBJECT="bees")
endif
	$(PYTHON) -m whatif.run --subject "$(SUBJECT)" $(if $(DRY_RUN),--dry-run,)

# Backwards-compatible alias (v2 used TOPIC=).
run-topic:
ifndef TOPIC
	$(error TOPIC is not set. Usage: make run-topic TOPIC="bees")
endif
	$(PYTHON) -m whatif.run --topic "$(TOPIC)" $(if $(DRY_RUN),--dry-run,)

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf .pytest_cache