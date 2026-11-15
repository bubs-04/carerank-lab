.PHONY: setup up down pipeline rebuild test test-unit test-ui e2e lint benchmark
setup:
	python3 scripts/setup_env.py
up: setup
	docker compose up --build -d
down:
	docker compose down
pipeline:
	docker compose run --rm seed python -m app.pipeline
rebuild:
	docker compose build --no-cache
	docker compose up -d
test:
	cd backend && python -m pytest -q
	cd frontend && npm test && npm run build
test-unit:
	cd backend && python -m pytest tests/test_scoring.py -q
test-ui:
	cd frontend && npm test
e2e:
	cd frontend && npm run e2e
lint:
	cd backend && ruff check . && ruff format --check .
benchmark:
	cd backend && python -m app.benchmark
