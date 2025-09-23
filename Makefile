.PHONY: run seed fmt test check

run:
	uvicorn app.main:app --reload

seed:
	python -m app.scripts.seed

fmt:
	python -m black app tests || true

test:
	pytest

check: fmt test
