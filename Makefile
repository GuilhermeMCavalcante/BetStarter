.PHONY: install init run-api run-dashboard pipeline lint format

PYTHON := python
PYTHONPATH := PYTHONPATH=.

install:
	$(PYTHON) -m pip install -r requirements.txt

init:
	$(PYTHONPATH) $(PYTHON) scripts/init_db.py

run-api:
	$(PYTHONPATH) uvicorn app.main:app --reload

run-dashboard:
	$(PYTHONPATH) $(PYTHON) -m streamlit run dashboard/dashboard.py

pipeline:
	$(PYTHONPATH) $(PYTHON) scripts/pipeline.py --days 7

docker-up:
	docker compose up --build

docker-down:
	docker compose down

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .
