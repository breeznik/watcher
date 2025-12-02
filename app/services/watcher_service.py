from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Optional
from uuid import uuid4
import logging
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from app.database import SessionLocal
from app.models import Watcher, CheckLog, StatusEnum
from app.emailer import send_email
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

MIN_RENDER_SECONDS = 30
MAX_RENDER_SECONDS = 180


@dataclass
class RenderStats:
    load_duration: float
    effective_timeout: float


class RenderTooHeavyError(Exception):
    def __init__(self, duration: float):
        self.duration = duration
        super().__init__(f"render exceeded {duration:.2f}s")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_html(url: str) -> str:
    logger.info(f"Fetching URL with requests: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=20)
    logger.info(
        "Requests response: status=%s, headers=%s",
        resp.status_code,
        {k: v for k, v in resp.headers.items() if k.lower() in {"server", "content-type", "cf-ray", "cf-cache-status"}},
    )
    resp.raise_for_status()
    html = resp.text
    logger.info(f"Fetched HTML length: {len(html)} chars")
    return html


def fetch_html_js(
    url: str,
    baseline_timeout: float,
    wait_selector: Optional[str] = None,
    screenshot_path: Optional[Path] = None,
) -> tuple[str, RenderStats]:
    logger.info(f"Fetching URL with Playwright (JS rendering): {url}")
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # optional dependency
        raise RuntimeError("playwright not installed; pip install playwright and run 'playwright install chromium'") from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York",
            )
            context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = {runtime: {}};
            """
            )
            page = context.new_page()
            start = perf_counter()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=MAX_RENDER_SECONDS * 1000)
            except PlaywrightTimeout as exc:
                duration = perf_counter() - start
                logger.warning("Playwright render timed out after %.2fs (cap %ss)", duration, MAX_RENDER_SECONDS)
                raise RenderTooHeavyError(duration) from exc
            load_duration = perf_counter() - start
            if load_duration >= MAX_RENDER_SECONDS:
                raise RenderTooHeavyError(load_duration)

            baseline_timeout = max(MIN_RENDER_SECONDS, min(MAX_RENDER_SECONDS, baseline_timeout))
            suggested_timeout = max(MIN_RENDER_SECONDS, min(MAX_RENDER_SECONDS, load_duration * 1.3))
            extra_wait = max(0.0, suggested_timeout - load_duration)
            extra_wait = max(extra_wait, max(0.0, baseline_timeout - load_duration))
            min_extra = max(0.0, float(settings.render_post_wait_seconds))
            extra_wait = max(extra_wait, min_extra)
            extra_wait = min(extra_wait, max(0.0, MAX_RENDER_SECONDS - min(load_duration, MAX_RENDER_SECONDS)))
            wait_budget_ms = int(extra_wait * 1000)
            if wait_selector and wait_budget_ms > 0:
                try:
                    page.wait_for_selector(wait_selector, timeout=wait_budget_ms)
                    wait_budget_ms = 0
                    logger.info("Playwright: selector '%s' appeared", wait_selector)
                except Exception:
                    logger.info("Playwright: selector '%s' NOT found before timeout", wait_selector)
            if wait_budget_ms > 0:
                page.wait_for_timeout(wait_budget_ms)

            if screenshot_path is not None:
                try:
                    page.screenshot(path=str(screenshot_path))
                    logger.info("Playwright: saved screenshot to %s", screenshot_path)
                except Exception as e:
                    logger.info("Playwright: failed saving screenshot: %s", e)
            html = page.content()
            logger.info(
                "Playwright fetched HTML length: %s chars (load %.2fs, wait %.2fs, target %.2fs)",
                len(html),
                load_duration,
                extra_wait,
                suggested_timeout,
            )
            return html, RenderStats(load_duration=load_duration, effective_timeout=suggested_timeout)
        finally:
            browser.close()


class WatcherScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=settings.timezone)
        self.render_timeouts: dict[int, float] = {}
        self.manual_checks_in_progress: set[int] = set()
        self.default_render_timeout = max(
            MIN_RENDER_SECONDS,
            min(MAX_RENDER_SECONDS, float(settings.render_timeout)),
        )

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
            coalesce=True,
        )

    def remove_job(self, watcher_id: int):
        job_id = self._job_id(watcher_id)
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

    def reschedule(self, watcher: Watcher):
        self._add_or_update_job(watcher)

    def _record_render_timeout(self, watcher_id: int, timeout: float):
        self.render_timeouts[watcher_id] = timeout

    def _detect(self, watcher: Watcher) -> tuple[StatusEnum, str | None]:
        logger.info(f"[Watcher #{watcher.id}] Starting check for URL: {watcher.url}")
        logger.info(f"[Watcher #{watcher.id}] Searching for phrase: '{watcher.phrase}'")
        try:
            html = fetch_html(watcher.url)
            phrase_lower = watcher.phrase.lower()
            if phrase_lower in html.lower():
                logger.info(f"[Watcher #{watcher.id}] Phrase FOUND in initial HTML (requests)")
                return StatusEnum.found, None
            logger.info(f"[Watcher #{watcher.id}] Phrase NOT found in initial HTML")
            # Optional: dump artifacts for evidence
            if settings.debug_dump_artifacts:
                try:
                    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    out_dir = Path(settings.debug_artifacts_dir) / f"watcher_{watcher.id}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / f"{ts}_requests.html").write_text(html, encoding="utf-8", errors="ignore")
                    logger.info("[Watcher #%s] Saved requests HTML to %s", watcher.id, out_dir)
                except Exception as e:
                    logger.info("[Watcher #%s] Failed to save requests HTML: %s", watcher.id, e)

            if settings.render_js:
                logger.info(f"[Watcher #{watcher.id}] RENDER_JS=true, attempting JS rendering...")
                baseline_timeout = self.render_timeouts.get(watcher.id, self.default_render_timeout)
                logger.info(
                    "[Watcher #%s] Baseline render target %.2fs",
                    watcher.id,
                    baseline_timeout,
                )
                screenshot_path: Optional[Path] = None
                wait_sel: Optional[str] = settings.debug_wait_selector
                if settings.debug_dump_artifacts:
                    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    out_dir = Path(settings.debug_artifacts_dir) / f"watcher_{watcher.id}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    screenshot_path = out_dir / f"{ts}_playwright.png"
                try:
                    html, render_stats = fetch_html_js(
                        watcher.url,
                        baseline_timeout=baseline_timeout,
                        wait_selector=wait_sel,
                        screenshot_path=screenshot_path,
                    )
                    self._record_render_timeout(watcher.id, render_stats.effective_timeout)
                    logger.info(
                        "[Watcher #%s] Render stats -> load %.2fs, target timeout %.2fs",
                        watcher.id,
                        render_stats.load_duration,
                        render_stats.effective_timeout,
                    )
                except RenderTooHeavyError as heavy_exc:
                    msg = (
                        f"JS render exceeded {MAX_RENDER_SECONDS}s (observed {heavy_exc.duration:.2f}s);"
                        " marked as heavy"
                    )
                    logger.warning("[Watcher #%s] %s", watcher.id, msg)
                    return StatusEnum.heavy, msg

                if phrase_lower in html.lower():
                    logger.info(f"[Watcher #{watcher.id}] Phrase FOUND after JS rendering")
                    return StatusEnum.found, None
                logger.info(f"[Watcher #{watcher.id}] Phrase NOT found even after JS rendering")
                if settings.debug_dump_artifacts:
                    try:
                        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                        out_dir = Path(settings.debug_artifacts_dir) / f"watcher_{watcher.id}"
                        (out_dir / f"{ts}_playwright.html").write_text(html, encoding="utf-8", errors="ignore")
                        logger.info("[Watcher #%s] Saved Playwright HTML to %s", watcher.id, out_dir)
                    except Exception as e:
                        logger.info("[Watcher #%s] Failed to save Playwright HTML: %s", watcher.id, e)
                return StatusEnum.not_found, None
            logger.info(f"[Watcher #{watcher.id}] RENDER_JS=false, skipping JS rendering")
            return StatusEnum.not_found, None
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[Watcher #{watcher.id}] Error during check: {exc}", exc_info=True)
            return StatusEnum.error, str(exc)[:500]

    def run_check(self, watcher_id: int, force: bool = False):
        try:
            with SessionLocal() as db:
                watcher = db.get(Watcher, watcher_id)
                if not watcher or (not watcher.enabled and not force):
                    logger.info(f"[Watcher #{watcher_id}] Skipping check (not found or disabled)")
                    return
                now = datetime.utcnow()

                status, error_message = self._detect(watcher)
                logger.info(f"[Watcher #{watcher.id}] Check result: {status}")

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
                    logger.info(f"[Watcher #{watcher.id}] Sending alert emails to {len(emails)} recipients")
                    subject = f"Watcher alert: phrase found for {watcher.url}"
                    body = (
                        f"Watcher #{watcher.id}\nURL: {watcher.url}\nPhrase: {watcher.phrase}\nTime: {now} UTC"
                    )
                    try:
                        send_email(emails, subject, body)
                        logger.info(f"[Watcher #{watcher.id}] Alert email sent successfully")
                    except Exception as e:
                        logger.error(f"[Watcher #{watcher.id}] Failed to send email: {e}")
        finally:
            if force and watcher_id in self.manual_checks_in_progress:
                self.manual_checks_in_progress.discard(watcher_id)
                logger.info(f"[Watcher #{watcher_id}] Manual check completed, cleared from in-progress")

    def manual_check(self, watcher_id: int) -> bool:
        if watcher_id in self.manual_checks_in_progress:
            logger.warning("[Watcher #%s] Manual check already in progress, ignoring request", watcher_id)
            return False
        
        self.manual_checks_in_progress.add(watcher_id)
        run_date = datetime.now(self.scheduler.timezone)
        job_id = f"manual-watcher-{watcher_id}-{uuid4().hex[:8]}"
        logger.info("[Watcher #%s] Queuing manual check as job %s", watcher_id, job_id)
        self.scheduler.add_job(
            self.run_check,
            trigger="date",
            run_date=run_date,
            args=[watcher_id],
            kwargs={"force": True},
            id=job_id,
            replace_existing=False,
            misfire_grace_time=MAX_RENDER_SECONDS,
        )
        return True


scheduler = WatcherScheduler()