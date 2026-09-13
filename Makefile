.PHONY: up down logs test build-all

up:
	docker compose up -d --wait

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest tests -v

build-all:
	python db/migrate.py
	python pipeline/build_relational.py data_clean
	python pipeline/build_search_index.py
