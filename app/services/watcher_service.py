from datetime import datetime
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from app.database import SessionLocal
from app.models import Watcher, CheckLog, StatusEnum
from app.emailer import send_email
from app.config import get_settings

settings = get_settings()

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def fetch_html_js(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # optional dependency
        raise RuntimeError("playwright not installed; pip install playwright and run 'playwright install chromium'") from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=settings.render_timeout * 1000)
        html = page.content()
        browser.close()
        return html


class WatcherScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=settings.timezone)

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()

    def load_and_schedule(self):
        with SessionLocal() as db:
            watchers = db.execute(select(Watcher).where(Watcher.enabled == True)).scalars().all()
            for watcher in watchers:
                self._add_or_update_job(watcher)

    def _job_id(self, watcher_id: int) -> str:
        return f"watcher-{watcher_id}"

    def _add_or_update_job(self, watcher: Watcher):
        if not watcher.enabled:
            self.remove_job(watcher.id)
            return
        self.scheduler.add_job(
            self.run_check,
            "interval",
            minutes=watcher.interval_minutes,
            id=self._job_id(watcher.id),
            replace_existing=True,
            args=[watcher.id],
            max_instances=1,
            misfire_grace_time=30,
        )

    def remove_job(self, watcher_id: int):
        job_id = self._job_id(watcher_id)
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

    def reschedule(self, watcher: Watcher):
        self._add_or_update_job(watcher)

    def _detect(self, watcher: Watcher) -> tuple[StatusEnum, str | None]:
        try:
            html = fetch_html(watcher.url)
            if watcher.phrase.lower() in html.lower():
                return StatusEnum.found, None
            if settings.render_js:
                html = fetch_html_js(watcher.url)
                if watcher.phrase.lower() in html.lower():
                    return StatusEnum.found, None
                return StatusEnum.not_found, None
            return StatusEnum.not_found, None
        except Exception as exc:  # noqa: BLE001
            return StatusEnum.error, str(exc)[:500]

    def run_check(self, watcher_id: int, force: bool = False):
        with SessionLocal() as db:
            watcher = db.get(Watcher, watcher_id)
            if not watcher or (not watcher.enabled and not force):
                return
            now = datetime.utcnow()

            status, error_message = self._detect(watcher)

            should_email = status == StatusEnum.found and watcher.emails

            watcher.last_check_at = now
            watcher.last_status = status
            watcher.last_error = error_message

            log_entry = CheckLog(
                watcher_id=watcher.id,
                checked_at=now,
                status=status,
                error_message=error_message,
            )
            db.add(log_entry)
            try:
                db.commit()
            except StaleDataError:
                db.rollback()
                self.remove_job(watcher_id)
                return
            except Exception:
                db.rollback()
                raise

            if should_email:
                emails = [e.strip() for e in watcher.emails.split(",") if e.strip()]
                if emails:
                    subject = f"Watcher alert: phrase found for {watcher.url}"
                    body = (
                        f"Watcher #{watcher.id}\nURL: {watcher.url}\nPhrase: {watcher.phrase}\nTime: {now} UTC"
                    )
                    try:
                        send_email(emails, subject, body)
                    except Exception:
                        pass

    def manual_check(self, watcher_id: int):
        self.run_check(watcher_id, force=True)


scheduler = WatcherScheduler()