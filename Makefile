.PHONY: install install-dev test run lint format clean

install:
	pip install -r requirements.txt
	pip install -e .

install-dev:
	pip install -r requirements-dev.txt
	pip install -e .

test:
	pytest tests/ -v

run:
	python -m toggl_track_slack_digest.main

lint:
	mypy src/

format:
	black src/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache
