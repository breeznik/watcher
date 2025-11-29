# Watcher - Webpage Phrase Monitoring

A FastAPI + APScheduler app that monitors webpages on intervals, detects phrases, and emails alerts.

## Features
- Create/manage multiple watchers (URL, phrase, interval, recipients, enable/disable)
- Background scheduler per watcher (APScheduler)
- Case-insensitive phrase search with request headers
- Email alerts on state change from `not_found` (or unknown) to `found`
- Logs per check, last 50 visible in UI
- Simple session login (env-configured credentials)
- REST API + server-rendered admin UI
- Docker + docker-compose + nginx reverse proxy (image installs Playwright + Chromium)
- Alembic migration included (initial schema)
- JS rendering via Playwright/Chromium for heavily client-side pages (Agoda, etc.)

## Quickstart (Docker)
1. Copy env template and adjust credentials and SMTP settings:
   ```bash
   cp .env.example .env
   ```
2. Build and run:
   ```bash
   docker compose up --build
   ```
3. Open http://localhost and sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`. Docker image already has Playwright + Chromium; set `RENDER_JS=true` to use JS rendering.

## Local development
```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Visit http://127.0.0.1:8000

## Environment variables
- `SECRET_KEY` session signing key
- `ADMIN_USERNAME`, `ADMIN_PASSWORD` login credentials
- `DATABASE_URL` e.g. `sqlite:///./data/data.db`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `FROM_EMAIL`
- `TIMEZONE` timezone for scheduler (e.g. `UTC`, `Asia/Kolkata`)
- `RENDER_JS` set `true` to enable Playwright rendering
- `RENDER_TIMEOUT` seconds to wait for JS render (default 20)

## JS rendering (for dynamic pages like Agoda)
- Install optional dependency and browser (if not using Docker image):
  ```bash
  pip install playwright==1.49.0
  python -m playwright install chromium
  ```
- Set `RENDER_JS=true` in `.env`. The watcher fetches with requests first, then JS-render if enabled.

## Database & migrations
- Uses SQLite by default; adjust `DATABASE_URL` for Postgres/MySQL, etc.
- Initial migration: `alembic upgrade head`
- Autogenerate new migration: `alembic revision --autogenerate -m "msg"`

## Systemd example (non-docker)
See `deploy/watcher.service.example`. Place project in `/opt/watcher`, set ownership, copy unit file to `/etc/systemd/system/`, then `systemctl enable --now watcher`.

## Project structure
- `app/main.py` FastAPI app & lifecycle
- `app/models.py` SQLAlchemy models
- `app/services/watcher_service.py` APScheduler jobs & checks
- `app/emailer.py` SMTP sender
- `app/templates/*` UI templates
- `deploy/nginx.conf` reverse proxy

## Notes
- Email alerts fire only when status transitions from `not_found` (or unknown) to `found`.
- Manual "Check Now" runs immediately without waiting for the next interval.
- JS rendering adds resource usage; keep `render_timeout` reasonable (10–30s).