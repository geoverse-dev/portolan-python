.PHONY: help setup test coverage lint typecheck check check-conformance check-conformance-read check-conformance-write check-conformance-all build clean

UV ?= uv
ADAPTER_PYTHON ?= $(UV) run python
CONFORMANCE_REPOSITORY ?= https://github.com/geoverse-dev/portolan-conformance.git
CONFORMANCE_VERSION ?= v0.1.1
CONFORMANCE ?= uvx --from 'git+$(CONFORMANCE_REPOSITORY)@$(CONFORMANCE_VERSION)' portolan-conformance
CONFORMANCE_REPORT ?= read-profile-report.json
CONFORMANCE_WRITE_REPORT ?= write-profile-report.json

help:
	@printf '%s\n' 'Targets: setup test coverage lint typecheck check check-conformance check-conformance-read check-conformance-write check-conformance-all build clean'

setup:
	$(UV) sync --extra dev

test:
	$(UV) run --extra dev pytest

coverage:
	$(UV) run --extra dev pytest --cov=portolan --cov-report=term-missing

lint:
	$(UV) run --extra dev ruff check .

typecheck:
	$(UV) run --extra dev mypy

check: lint typecheck test

check-conformance: check-conformance-read

check-conformance-all: check-conformance-read check-conformance-write

check-conformance-read:
	$(CONFORMANCE) run \
		--profile read \
		--adapter '$(ADAPTER_PYTHON) $(CURDIR)/tests/conformance_adapter.py' \
		--report '$(CONFORMANCE_REPORT)'

check-conformance-write:
	$(CONFORMANCE) run \
		--profile write \
		--adapter '$(ADAPTER_PYTHON) $(CURDIR)/tests/conformance_adapter.py' \
		--report '$(CONFORMANCE_WRITE_REPORT)'

build:
	$(UV) build

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache .mypy_cache htmlcov
