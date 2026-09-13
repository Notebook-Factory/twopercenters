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
	# 1. migrate: apply any pending schema migrations.
	python db/migrate.py
	# 2. load: load every edition, in ascending data-year order, then export
	#    Parquet, then refresh group_metrics (R24 -- see build() in
	#    pipeline/build_relational.py; the refresh is folded into this step
	#    since it must run after the data is loaded, not before).
	python pipeline/build_relational.py data_clean
	# 3. search index: build the Elasticsearch index from the relational core.
	python pipeline/build_search_index.py
