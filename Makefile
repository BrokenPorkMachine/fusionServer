.PHONY: run seed fmt

run:
	uvicorn app.main:app --reload

seed:
	python -m app.scripts.seed

fmt:
	python -m black app || true
