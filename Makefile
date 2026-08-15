.PHONY: install test init serve ca500 rank joins runs changes
install:
	python -m pip install -e '.[dev]'

test:
	pytest -q

init:
	fia init-db

serve:
	fia serve

ca500:
	fia ingest california --bucket 500_plus

rank:
	fia rank --limit 50 --min-score 50

joins:
	fia joins --limit 100

runs:
	fia runs --limit 50

changes:
	fia changes --limit 50
