PY=python

.PHONY: up down api bot install-backend install-bot install-ingestion

up:
	docker compose up -d

down:
	docker compose down

install-backend:
	cd backend && $(PY) -m venv .venv && .\.venv\Scripts\pip install -U pip && .\.venv\Scripts\pip install -r requirements.txt

install-bot:
	cd bot && $(PY) -m venv .venv && .\.venv\Scripts\pip install -U pip && .\.venv\Scripts\pip install -r requirements.txt

install-ingestion:
	cd ingestion && $(PY) -m venv .venv && .\.venv\Scripts\pip install -U pip && .\.venv\Scripts\pip install -r requirements.txt

api:
	cd backend && .\.venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && python -m http.server 3000

bot:
	cd bot && .\.venv\Scripts\python bot.py


