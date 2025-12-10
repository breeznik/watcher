from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Optional
from uuid import uuid4
import logging
from zoneinfo import ZoneInfo
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from app.db.database import SessionLocal
from app.db.models import Watcher, CheckLog, StatusEnum
from app.services.emailer import send_email
from app.core.config import get_settings
from app.services.enhanced_monitor import EnhancedMonitor
from app.core.stealth_config import MonitoringConfig, load_config_from_file

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


def _format_checked_times(checked_at: datetime) -> tuple[str, str]:
    """Return local/UTC time strings for emails."""
    try:
        tz = ZoneInfo(settings.timezone)
    except Exception:
        logger.warning("Invalid timezone '%s', defaulting to UTC", settings.timezone)
        tz = timezone.utc
    local_dt = checked_at.replace(tzinfo=timezone.utc).astimezone(tz)
    local_str = local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    utc_str = checked_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    return local_str, utc_str


# Legacy functions removed in favor of EnhancedMonitor



class WatcherScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=settings.timezone)
        self.render_timeouts: dict[int, float] = {}
        self.manual_checks_in_progress: set[int] = set()
        
        # Initialize EnhancedMonitor with settings
        config = None
        config_path = Path("app/core/monitoring_config.yaml")
        if config_path.exists():
            try:
                config = load_config_from_file(str(config_path))
                logger.info(f"Loaded EnhancedMonitor config from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load config from {config_path}: {e}")

        self.monitor = EnhancedMonitor(config)
        # Override with critical environment settings
        self.monitor.config.rendering.max_timeout = float(settings.render_timeout)
        self.monitor.config.debug_mode = settings.debug_dump_artifacts
        self.monitor.config.artifact_dir = settings.debug_artifacts_dir

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
            # Use EnhancedMonitor for robust detection
            wait_sel = settings.debug_wait_selector
            
            # Construct filenames for artifacts if debug is on
            screenshot_path = None
            html_dump_path = None
            if settings.debug_dump_artifacts:
                ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                out_dir = Path(settings.debug_artifacts_dir) / f"watcher_{watcher.id}"
                out_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = str(out_dir / f"{ts}_screenshot.png")
                html_dump_path = str(out_dir / f"{ts}_content.html")

            found, msg, metrics = self.monitor.monitor_url(
                url=watcher.url,
                target_phrase=watcher.phrase,
                selector=wait_sel,
                screenshot_path=screenshot_path,
                html_dump_path=html_dump_path
            )
            
            self.monitor.generate_diff_report(metrics, f"{settings.debug_artifacts_dir}/reports/{watcher.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            
            if found:
                logger.info(f"[Watcher #{watcher.id}] Phrase FOUND: {msg}")
                return StatusEnum.found, None
            
            if metrics.get('final_status') == 'failed':
                return StatusEnum.error, msg
                
            logger.info(f"[Watcher #{watcher.id}] Phrase NOT found: {msg}")
            return StatusEnum.not_found, None
            
        except Exception as exc:
            logger.error(f"[Watcher #{watcher.id}] Error during check: {exc}", exc_info=True)
            return StatusEnum.error, str(exc)[:500]

    def run_check(self, watcher_id: int, force: bool = False):
        email_context: dict | None = None
        log_id: int | None = None
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
                
                if should_email:
                    local_ts, utc_ts = _format_checked_times(now)
                    email_context = {
                        "recipients": [e.strip() for e in watcher.emails.split(",") if e.strip()],
                        "local_ts": local_ts,
                        "utc_ts": utc_ts,
                        "watcher_name": watcher.name,
                        "watcher_url": watcher.url,
                        "watcher_phrase": watcher.phrase,
                        "watcher_id": watcher.id,
                    }

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
                    db.refresh(log_entry)  # Get the log entry ID
                    log_id = log_entry.id
                except StaleDataError:
                    db.rollback()
                    self.remove_job(watcher_id)
                    return
                except Exception:
                    db.rollback()
                    raise

            # Send email notification if needed
            if should_email and email_context and email_context.get("recipients"):
                logger.info(
                    f"[Watcher #{watcher_id}] Sending alert emails to {len(email_context['recipients'])} recipients"
                )
                email_subject = f"[Watcher] {email_context['watcher_name']} - phrase found"
                email_lines = [
                    "A watched phrase was detected.",
                    "",
                    f"Watcher : #{email_context['watcher_id']} ({email_context['watcher_name']})",
                    f"URL     : {email_context['watcher_url']}",
                    f"Phrase  : {email_context['watcher_phrase']}",
                    f"Checked : {email_context['local_ts']}",
                    f"UTC     : {email_context['utc_ts']}",
                    f"Log ID  : {log_id}" if log_id is not None else None,
                ]
                email_body = "\n".join(line for line in email_lines if line is not None)
                email_sent = False
                email_error = None
                try:
                    send_email(email_context["recipients"], email_subject, email_body)
                    logger.info(f"[Watcher #{watcher_id}] Alert email sent successfully")
                    email_sent = True
                except Exception as e:
                    email_error = str(e)[:500]
                    logger.error(f"[Watcher #{watcher_id}] Failed to send email: {e}")
                
                # Update log entry with email status
                with SessionLocal() as db:
                    log_entry = db.get(CheckLog, log_id)
                    if log_entry:
                        log_entry.email_sent = email_sent
                        log_entry.email_error = email_error
                        try:
                            db.commit()
                        except Exception as e:
                            logger.error(f"[Watcher #{watcher_id}] Failed to update email status in log: {e}")
                            db.rollback()
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