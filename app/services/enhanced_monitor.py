import logging
import time
import random
import json
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timedelta
import hashlib
import sqlite3
from urllib.parse import urlparse
import requests
import Levenshtein
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from app.core.stealth_config import (
    MonitoringConfig, load_config_from_file, parse_cli_args,
    create_default_config_file, UserAgentConfig, HeaderConfig
)
import pytesseract
from PIL import Image
import io

logger = logging.getLogger(__name__)

class EnhancedMonitor:
    """
    Enhanced Playwright-based monitoring system with stealth, smart rendering,
    session persistence, and resilience features.
    """

    def __init__(self, config: Optional[MonitoringConfig] = None):
        self.config = config or MonitoringConfig()
        self.setup_logging()
        self.cookie_db_path = Path(self.config.session.cookie_storage_path) / "cookies.db"
        self.ensure_cookie_storage()
        self.current_session_id = None
        self.session_start_time = None

    def setup_logging(self):
        """Configure logging based on settings."""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper(), logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def ensure_cookie_storage(self):
        """Ensure cookie storage database exists."""
        self.cookie_db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.cookie_db_path)
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cookies (
                    domain TEXT PRIMARY KEY,
                    cookies TEXT,
                    last_updated TIMESTAMP,
                    expires TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    domain TEXT,
                    created_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    context_data TEXT
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def get_cookies_for_domain(self, domain: str) -> Optional[List[Dict]]:
        """Retrieve stored cookies for a domain."""
        conn = sqlite3.connect(self.cookie_db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT cookies, expires FROM cookies
                WHERE domain = ? AND (expires IS NULL OR expires > CURRENT_TIMESTAMP)
            ''', (domain,))

            result = cursor.fetchone()
            if result:
                cookies_data, expires = result
                return json.loads(cookies_data)
            return None
        finally:
            conn.close()

    def save_cookies_for_domain(self, domain: str, cookies: List[Dict]):
        """Store cookies for a domain."""
        expires = (datetime.now() + timedelta(
            days=self.config.session.cookie_expiration_days
        )).isoformat()

        conn = sqlite3.connect(self.cookie_db_path)
        try:
            conn.execute('''
                INSERT OR REPLACE INTO cookies (domain, cookies, last_updated, expires)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''', (domain, json.dumps(cookies), expires))
            conn.commit()
        finally:
            conn.close()

    def start_new_session(self, domain: str) -> str:
        """Start a new monitoring session."""
        session_id = hashlib.md5(f"{domain}_{datetime.now().isoformat()}".encode()).hexdigest()
        expires_at = (datetime.now() + timedelta(
            seconds=self.config.session.session_ttl_seconds
        )).isoformat()

        conn = sqlite3.connect(self.cookie_db_path)
        try:
            conn.execute('''
                INSERT INTO sessions (session_id, domain, created_at, expires_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''', (session_id, domain, expires_at))
            conn.commit()
        finally:
            conn.close()

        self.current_session_id = session_id
        self.session_start_time = datetime.now()
        return session_id

    def get_active_session(self, domain: str) -> Optional[str]:
        """Get active session for domain if it exists and is valid."""
        conn = sqlite3.connect(self.cookie_db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT session_id FROM sessions
                WHERE domain = ? AND expires_at > CURRENT_TIMESTAMP
                ORDER BY created_at DESC LIMIT 1
            ''', (domain,))

            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

    def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        conn = sqlite3.connect(self.cookie_db_path)
        try:
            conn.execute('DELETE FROM sessions WHERE expires_at <= CURRENT_TIMESTAMP')
            conn.execute('DELETE FROM cookies WHERE expires <= CURRENT_TIMESTAMP')
            conn.commit()
        finally:
            conn.close()

    def get_stealth_headers(self, url: str) -> Dict[str, str]:
        """Generate stealth headers for the request."""
        domain = urlparse(url).netloc
        headers = {
            "User-Agent": self.config.stealth.user_agents.get_random_agent(),
            "Accept-Language": self.config.stealth.headers.accept_language,
            "DNT": self.config.stealth.headers.dnt,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

        if self.config.stealth.headers.referer:
            headers["Referer"] = self.config.stealth.headers.referer
        else:
            headers["Referer"] = f"https://www.google.com/search?q={domain}"

        if self.config.stealth.headers.custom_headers:
            headers.update(self.config.stealth.headers.custom_headers)

        return headers

    def get_viewport_size(self) -> Tuple[int, int]:
        """Get randomized viewport size."""
        if self.config.stealth.randomize_viewport:
            width = random.randint(*self.config.stealth.viewport_width_range)
            height = random.randint(*self.config.stealth.viewport_height_range)
            return width, height
        return 1920, 1080

    def apply_stealth_overrides(self, context):
        """Apply stealth overrides to the browser context."""
        stealth_script = []

        if self.config.stealth.enable_webdriver_masking:
            stealth_script.append(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

        if self.config.stealth.enable_plugin_masking:
            stealth_script.append(
                "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
            )
            stealth_script.append(
                "Object.defineProperty(navigator, 'mimeTypes', {get: () => [1, 2, 3, 4, 5]});"
            )

        if self.config.stealth.enable_language_masking:
            stealth_script.append(
                "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
            )
            stealth_script.append(
                "Object.defineProperty(navigator, 'language', {get: () => 'en-US'});"
            )

        if self.config.stealth.enable_chrome_runtime:
            stealth_script.append("window.chrome = {runtime: {}, app: {}};")
            stealth_script.append("window.navigator.chrome = {runtime: {}, app: {}};")

        # Additional stealth measures
        stealth_script.extend([
            "Object.defineProperty(navigator, 'permissions', {get: () => ({query: () => Promise.resolve({state: 'denied'})})});",
            "Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4});",
            "Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});",
            "Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});",
            "Object.defineProperty(window, 'outerWidth', {get: () => 1920});",
            "Object.defineProperty(window, 'outerHeight', {get: () => 1080});",
            "Object.defineProperty(screen, 'width', {get: () => 1920});",
            "Object.defineProperty(screen, 'height', {get: () => 1080});"
        ])

        if stealth_script:
            context.add_init_script("\n".join(stealth_script))

    def apply_request_throttling(self):
        """Apply request throttling if configured."""
        if self.config.stealth.request_throttling > 0:
            time.sleep(self.config.stealth.request_throttling)

    def perform_smart_interactions(self, page, url: str):
        """Perform smart interactions to trigger dynamic content loading."""
        logger.info(f"Performing smart interactions for {url}")

        # Robust key-based scrolling to trigger lazy loading
        # This uses the proven logic from the verification phase
        last_height = page.evaluate("document.body.scrollHeight")
        logger.info(f"Smart Interactions: initial height {last_height}, starting keyboard scroll...")
        
        max_scrolls = 30
        consecutive_stable_checks = 0
        required_stable_checks = 3 
        
        for i in range(max_scrolls):
            # Press End to go to bottom
            page.keyboard.press("End")
            
            # Wait for load - generous wait
            page.wait_for_timeout(3000)
            
            new_height = page.evaluate("document.body.scrollHeight")
            
            if new_height == last_height:
                consecutive_stable_checks += 1
                logger.debug(f"Smart Interactions: height stable ({new_height}) for {consecutive_stable_checks}/{required_stable_checks}")
                
                if consecutive_stable_checks >= required_stable_checks:
                    logger.info("Smart Interactions: page fully loaded (stable height). Stopping scroll.")
                    break
                    
                # Aggressive Shake: Back up a bit to re-trigger intersection
                logger.debug("Smart Interactions: keyboard shake (PageUp x 3) to unstick...")
                for _ in range(3):
                    page.keyboard.press("PageUp")
                    page.wait_for_timeout(500)
                
                # Press End again to re-approach
                page.keyboard.press("End")
            else:
                consecutive_stable_checks = 0 
                logger.info(f"Smart Interactions: scroll {i+1}/{max_scrolls}, height increased {last_height}->{new_height}")
                last_height = new_height

        # Hover over potential trigger elements
        for selector in self.config.rendering.hover_selectors:
            try:
                elements = page.locator(selector)
                count = elements.count()
                if count > 0:
                    logger.debug(f"Found {count} elements matching hover selector: {selector}")
                    for i in range(min(count, 3)):  # Hover over first 3 elements
                        elements.nth(i).hover()
                        time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Error hovering over {selector}: {e}")

        # Click load more buttons if visible
        for selector in self.config.rendering.click_selectors:
            try:
                button = page.locator(selector)
                if button.count() > 0 and button.first.is_visible():
                    logger.info(f"Clicking load more button: {selector}")
                    button.first.click()
                    time.sleep(2)  # Wait for content to load
                    break  # Only click the first matching button
            except Exception as e:
                logger.debug(f"Error clicking {selector}: {e}")

        # Try text-based selectors for load more buttons
        for selector in self.config.rendering.load_more_button_selectors:
            try:
                button = page.locator(selector)
                if button.count() > 0 and button.first.is_visible():
                    logger.info(f"Clicking text-based load more button: {selector}")
                    button.first.click()
                    time.sleep(2)  # Wait for content to load
                    break  # Only click the first matching button
            except Exception as e:
                logger.debug(f"Error clicking text-based button {selector}: {e}")

    def validate_content_visibility(self, page, selector: str) -> bool:
        """Validate that content is actually visible and not hidden."""
        try:
            element = page.locator(selector)
            if element.count() == 0:
                return False

            # Check if element is visible
            if not element.first.is_visible():
                return False

            # Check if element has content
            text = element.first.inner_text().strip()
            if not text:
                return False

            # Check if element is not hidden by CSS
            style = element.first.evaluate("el => window.getComputedStyle(el)")
            if style.get('display') == 'none' or style.get('visibility') == 'hidden':
                return False

            return True
        except Exception as e:
            logger.debug(f"Error validating visibility for {selector}: {e}")
            return False

    def calculate_exponential_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        if self.config.resilience.retry_strategy != "exponential_backoff":
            return 0.0

        base = self.config.resilience.backoff_base
        max_delay = self.config.resilience.backoff_max

        # Calculate delay: base * 2^(attempt-1), but don't exceed max
        delay = min(base * (2 ** (attempt - 1)), max_delay)
        return delay

    def perform_ocr_fallback(self, page, screenshot_path: Optional[str] = None) -> str:
        """Perform OCR on page content as fallback."""
        if not self.config.resilience.ocr_enabled:
            return ""

        try:
            # Take screenshot if not provided
            if not screenshot_path:
                screenshot_path = f"temp_screenshot_{int(time.time())}.png"
                page.screenshot(path=screenshot_path)

            # Perform OCR
            image = Image.open(screenshot_path)
            text = pytesseract.image_to_string(image)
            return text
        except Exception as e:
            logger.warning(f"OCR fallback failed: {e}")
            return ""
        finally:
            # Clean up temporary screenshot
            if screenshot_path and "temp_screenshot" in screenshot_path:
                try:
                    os.remove(screenshot_path)
                except:
                    pass

    def check_wayback_machine(self, url: str) -> Optional[str]:
        """Check Wayback Machine for archived version of the page."""
        if not self.config.resilience.wayback_enabled:
            return None

        try:
            wayback_url = f"http://archive.org/wayback/available?url={url}"
            response = requests.get(wayback_url, timeout=10)
            data = response.json()

            if "archived_snapshots" in data and data["archived_snapshots"]:
                closest = data["archived_snapshots"]["closest"]
                archive_url = closest["url"]
                logger.info(f"Found Wayback Machine archive: {archive_url}")

                # Fetch the archived content
                archive_response = requests.get(archive_url, timeout=15)
                return archive_response.text

        except Exception as e:
            logger.warning(f"Wayback Machine check failed: {e}")

        return None

    def fuzzy_match_content(self, content: str, target_phrase: str) -> bool:
        """Perform fuzzy matching using Levenshtein distance."""
        if not self.config.resilience.fuzzy_match_enabled:
            return False

        try:
            # Find the best match in the content
            words = content.split()
            target_words = target_phrase.split()

            for word in words:
                for target_word in target_words:
                    distance = Levenshtein.distance(word.lower(), target_word.lower())
                    max_len = max(len(word), len(target_word))
                    similarity = 100 * (1 - distance / max_len) if max_len > 0 else 0

                    if similarity >= self.config.resilience.fuzzy_match_threshold:
                        logger.info(f"Fuzzy match found: '{word}' vs '{target_word}' ({similarity:.1f}% similarity)")
                        return True

            return False
        except Exception as e:
            logger.warning(f"Fuzzy matching failed: {e}")
            return False

    def should_retry_based_on_size(self, current_content: str, previous_content: Optional[str] = None) -> bool:
        """Determine if retry is needed based on content size thresholds."""
        if not previous_content:
            return False

        current_size = len(current_content)
        previous_size = len(previous_content)

        # If current content is significantly smaller than previous, consider retry
        size_ratio = current_size / previous_size if previous_size > 0 else 1.0

        if size_ratio < self.config.resilience.size_threshold_percentage:
            logger.info(f"Content size ratio {size_ratio:.2f} < threshold {self.config.resilience.size_threshold_percentage}, will retry")
            return True

        return False

    def monitor_url(
        self,
        url: str,
        target_phrase: str,
        selector: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        html_dump_path: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Enhanced URL monitoring with all stealth, rendering, and resilience features.

        Returns:
            Tuple of (found: bool, message: str, metrics: Dict)
        """
        start_time = time.time()
        domain = urlparse(url).netloc
        metrics = {
            'start_time': start_time,
            'url': url,
            'target_phrase': target_phrase,
            'attempts': 0,
            'final_status': 'pending',
            'execution_time': 0,
            'steps': []
        }

        # Clean up expired sessions
        self.cleanup_expired_sessions()

        # Check for existing session
        existing_session = self.get_active_session(domain)
        if existing_session:
            logger.info(f"Reusing existing session: {existing_session}")
            self.current_session_id = existing_session
        else:
            logger.info("Starting new monitoring session")
            self.start_new_session(domain)

        # Get stored cookies for this domain
        stored_cookies = self.get_cookies_for_domain(domain)

        attempt = 0
        last_content = None

        while attempt <= self.config.resilience.max_retries:
            attempt += 1
            metrics['attempts'] = attempt
            attempt_start = time.time()

            try:
                self.apply_request_throttling()
                step_start = time.time()

                with sync_playwright() as p:
                    # Configure browser launch
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-features=IsolateOrigins,site-per-process",
                            "--disable-infobars",
                            "--disable-notifications",
                            "--disable-geolocation",
                            "--disable-sync",
                            "--metrics-recording-only",
                            "--no-sandbox",
                            "--disable-setuid-sandbox"
                        ]
                    )

                    try:
                        # Create browser context with stealth settings
                        width, height = self.get_viewport_size()
                        context = browser.new_context(
                            viewport={"width": width, "height": height},
                            user_agent=self.config.stealth.user_agents.get_random_agent(),
                            locale="en-US",
                            timezone_id="America/New_York",
                            ignore_https_errors=True,
                            bypass_csp=True
                        )

                        # Apply stealth overrides
                        self.apply_stealth_overrides(context)

                        # Add stored cookies if available
                        if stored_cookies:
                            context.add_cookies(stored_cookies)
                            logger.info(f"Added {len(stored_cookies)} stored cookies")

                        page = context.new_page()
                        metrics['steps'].append({
                            'step': 'browser_launch',
                            'timestamp': time.time(),
                            'duration': time.time() - step_start
                        })

                        # Navigate to URL with smart waiting
                        step_start = time.time()
                        logger.info(f"Attempt {attempt}: Navigating to {url}")

                        try:
                            page.goto(
                                url,
                                wait_until="domcontentloaded",
                                timeout=int(self.config.rendering.max_timeout * 1000)
                            )
                        except PlaywrightTimeout:
                            logger.warning(f"DOM content load timeout, continuing with partial content")
                            # Continue with whatever content we have

                        metrics['steps'].append({
                            'step': 'navigation',
                            'timestamp': time.time(),
                            'duration': time.time() - step_start
                        })

                        # Smart interactions to trigger dynamic content
                        step_start = time.time()
                        self.perform_smart_interactions(page, url)
                        metrics['steps'].append({
                            'step': 'smart_interactions',
                            'timestamp': time.time(),
                            'duration': time.time() - step_start
                        })

                        # Wait for specific selector if provided
                        if selector:
                            step_start = time.time()
                            try:
                                page.wait_for_selector(
                                    selector,
                                    timeout=int(self.config.rendering.poll_interval * 1000)
                                )
                                logger.info(f"Selector '{selector}' found")
                            except Exception as e:
                                logger.warning(f"Selector '{selector}' not found: {e}")
                            metrics['steps'].append({
                                'step': 'selector_wait',
                                'timestamp': time.time(),
                                'duration': time.time() - step_start,
                                'selector': selector,
                                'found': page.locator(selector).count() > 0
                            })

                        # Get page content
                        step_start = time.time()
                        content = page.content()
                        metrics['steps'].append({
                            'step': 'content_extraction',
                            'timestamp': time.time(),
                            'duration': time.time() - step_start,
                            'content_length': len(content)
                        })

                        # Take screenshot if requested
                        if screenshot_path:
                            step_start = time.time()
                            try:
                                page.screenshot(path=screenshot_path)
                                logger.info(f"Saved screenshot to {screenshot_path}")
                            except Exception as e:
                                logger.warning(f"Failed to save screenshot: {e}")
                            metrics['steps'].append({
                                'step': 'screenshot',
                                'timestamp': time.time(),
                                'duration': time.time() - step_start,
                                'path': screenshot_path
                            })

                        # Dump HTML if requested
                        if html_dump_path:
                            step_start = time.time()
                            try:
                                Path(html_dump_path).parent.mkdir(parents=True, exist_ok=True)
                                with open(html_dump_path, 'w', encoding='utf-8') as f:
                                    f.write(content)
                                logger.info(f"Saved HTML to {html_dump_path}")
                            except Exception as e:
                                logger.warning(f"Failed to save HTML: {e}")
                            metrics['steps'].append({
                                'step': 'html_dump',
                                'timestamp': time.time(),
                                'duration': time.time() - step_start,
                                'path': html_dump_path
                            })

                        # Store cookies for future use
                        step_start = time.time()
                        cookies = context.cookies()
                        if cookies:
                            self.save_cookies_for_domain(domain, cookies)
                            logger.info(f"Saved {len(cookies)} cookies for {domain}")
                        metrics['steps'].append({
                            'step': 'cookie_storage',
                            'timestamp': time.time(),
                            'duration': time.time() - step_start,
                            'cookies_stored': len(cookies) if cookies else 0
                        })

                        # Check for target phrase in content
                        step_start = time.time()
                        found = target_phrase.lower() in content.lower()

                        if not found and self.config.resilience.fuzzy_match_enabled:
                            found = self.fuzzy_match_content(content, target_phrase)

                        if not found and self.config.resilience.ocr_enabled:
                            ocr_text = self.perform_ocr_fallback(page)
                            if ocr_text:
                                found = target_phrase.lower() in ocr_text.lower()
                                if found:
                                    metrics['steps'].append({
                                        'step': 'ocr_fallback_success',
                                        'timestamp': time.time(),
                                        'duration': time.time() - step_start,
                                        'method': 'ocr'
                                    })
                            else:
                                metrics['steps'].append({
                                    'step': 'ocr_fallback_failed',
                                    'timestamp': time.time(),
                                    'duration': time.time() - step_start,
                                    'method': 'ocr'
                                })

                        if not found and self.config.resilience.wayback_enabled:
                            wayback_content = self.check_wayback_machine(url)
                            if wayback_content:
                                found = target_phrase.lower() in wayback_content.lower()
                                if found:
                                    metrics['steps'].append({
                                        'step': 'wayback_fallback_success',
                                        'timestamp': time.time(),
                                        'duration': time.time() - step_start,
                                        'method': 'wayback'
                                    })
                            else:
                                metrics['steps'].append({
                                    'step': 'wayback_fallback_failed',
                                    'timestamp': time.time(),
                                    'duration': time.time() - step_start,
                                    'method': 'wayback'
                                })

                        metrics['steps'].append({
                            'step': 'content_analysis',
                            'timestamp': time.time(),
                            'duration': time.time() - step_start,
                            'target_found': found,
                            'content_length': len(content)
                        })

                        if found:
                            metrics['final_status'] = 'success'
                            message = f"Target phrase '{target_phrase}' found on {url}"
                            logger.info(message)

                            # Save final cookies
                            final_cookies = context.cookies()
                            if final_cookies:
                                self.save_cookies_for_domain(domain, final_cookies)

                            return True, message, metrics

                        # Check if we should retry based on content size
                        if last_content and self.should_retry_based_on_size(content, last_content):
                            logger.info("Content size threshold not met, will retry")
                            last_content = content
                            continue

                        last_content = content

                    finally:
                        browser.close()

                # Calculate backoff for next attempt
                if attempt < self.config.resilience.max_retries:
                    backoff_delay = self.calculate_exponential_backoff(attempt)
                    if backoff_delay > 0:
                        logger.info(f"Waiting {backoff_delay:.2f}s before retry attempt {attempt + 1}")
                        time.sleep(backoff_delay)

            except Exception as e:
                error_msg = f"Attempt {attempt} failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                metrics['steps'].append({
                    'step': 'error',
                    'timestamp': time.time(),
                    'duration': time.time() - attempt_start,
                    'error': str(e),
                    'attempt': attempt
                })

                if attempt >= self.config.resilience.max_retries:
                    metrics['final_status'] = 'failed'
                    return False, f"All {self.config.resilience.max_retries} attempts failed", metrics

        # If we get here, all retries exhausted without success
        metrics['final_status'] = 'not_found'
        message = f"Target phrase '{target_phrase}' not found after {self.config.resilience.max_retries} attempts"
        logger.warning(message)
        return False, message, metrics

    def generate_diff_report(self, metrics: Dict[str, Any], report_path: str):
        """Generate a detailed diff report of the monitoring process."""
        report_dir = Path(report_path).parent
        report_dir.mkdir(parents=True, exist_ok=True)

        # Create HTML report
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Monitoring Report - {metrics['url']}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
                h1 {{ color: #333; }}
                h2 {{ color: #666; margin-top: 20px; }}
                .success {{ color: green; font-weight: bold; }}
                .failed {{ color: red; font-weight: bold; }}
                .warning {{ color: orange; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                .step-row {{ cursor: pointer; }}
                .step-details {{ display: none; margin-left: 20px; padding: 10px; background: #f5f5f5; }}
            </style>
        </head>
        <body>
            <h1>Monitoring Report</h1>

            <h2>Summary</h2>
            <p><strong>URL:</strong> {metrics['url']}</p>
            <p><strong>Target Phrase:</strong> {metrics['target_phrase']}</p>
            <p><strong>Status:</strong> <span class="{'success' if metrics['final_status'] == 'success' else 'failed'}">
                {metrics['final_status'].upper()}
            </span></p>
            <p><strong>Attempts:</strong> {metrics['attempts']}</p>
            <p><strong>Execution Time:</strong> {metrics['execution_time']:.2f}s</p>

            <h2>Timeline</h2>
            <table>
                <thead>
                    <tr>
                        <th>Step</th>
                        <th>Timestamp</th>
                        <th>Duration (s)</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
        """

        # Add step rows
        for i, step in enumerate(metrics['steps']):
            step_name = step['step'].replace('_', ' ').title()
            timestamp = datetime.fromtimestamp(step['timestamp']).strftime('%H:%M:%S')
            duration = step['duration']

            # Add additional details based on step type
            details = []
            if 'selector' in step:
                details.append(f"Selector: {step['selector']}")
            if 'found' in step:
                details.append(f"Found: {step['found']}")
            if 'content_length' in step:
                details.append(f"Content: {step['content_length']} chars")
            if 'error' in step:
                details.append(f"Error: {step['error']}")
            if 'method' in step:
                details.append(f"Method: {step['method']}")

            details_str = ", ".join(details) if details else "N/A"

            html_content += f"""
                <tr class="step-row" onclick="toggleDetails({i})">
                    <td>{step_name}</td>
                    <td>{timestamp}</td>
                    <td>{duration:.3f}</td>
                    <td>{details_str}</td>
                </tr>
                <tr id="details-{i}" class="step-details">
                    <td colspan="4">
                        <pre>{json.dumps(step, indent=2)}</pre>
                    </td>
                </tr>
            """

        html_content += """
                </tbody>
            </table>

            <h2>Raw Metrics</h2>
            <pre>""" + json.dumps(metrics, indent=2) + """</pre>

            <script>
                function toggleDetails(index) {
                    const details = document.getElementById('details-' + index);
                    if (details.style.display === 'none') {
                        details.style.display = 'table-row';
                    } else {
                        details.style.display = 'none';
                    }
                }
            </script>
        </body>
        </html>
        """

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Generated report: {report_path}")

def create_enhanced_monitor_from_args() -> EnhancedMonitor:
    """Create EnhancedMonitor instance from command line arguments."""
    args = parse_cli_args()

    # Load config from file if specified
    config = None
    if args.config:
        try:
            config = load_config_from_file(args.config)
        except Exception as e:
            logger.error(f"Failed to load config from {args.config}: {e}")
            # Fall back to default config

    # Create monitor instance
    monitor = EnhancedMonitor(config)

    # Apply CLI overrides
    if args.debug:
        monitor.config.debug_mode = True
        monitor.config.log_level = "DEBUG"

    return monitor

def main():
    """Main entry point for enhanced monitoring."""
    monitor = create_enhanced_monitor_from_args()
    args = parse_cli_args()

    if not args.url or not args.phrase:
        print("Error: --url and --phrase are required")
        return

    # Generate timestamp for output files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(monitor.config.artifact_dir) / f"monitor_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    screenshot_path = None
    html_dump_path = None

    if args.screenshot:
        screenshot_path = str(output_dir / "screenshot.png")

    if args.html_dump:
        html_dump_path = str(output_dir / "content.html")

    # Perform monitoring
    found, message, metrics = monitor.monitor_url(
        url=args.url,
        target_phrase=args.phrase,
        selector=args.selector,
        screenshot_path=screenshot_path,
        html_dump_path=html_dump_path
    )

    # Calculate total execution time
    metrics['execution_time'] = time.time() - metrics['start_time']

    # Generate report
    report_path = str(output_dir / "report.html")
    monitor.generate_diff_report(metrics, report_path)

    # Output results
    print(f"\n{'='*50}")
    print(f"MONITORING RESULTS")
    print(f"{'='*50}")
    print(f"URL: {args.url}")
    print(f"Target Phrase: {args.phrase}")
    print(f"Status: {'FOUND' if found else 'NOT FOUND'}")
    print(f"Message: {message}")
    print(f"Attempts: {metrics['attempts']}")
    print(f"Execution Time: {metrics['execution_time']:.2f}s")
    print(f"Report: {report_path}")
    if screenshot_path:
        print(f"Screenshot: {screenshot_path}")
    if html_dump_path:
        print(f"HTML Dump: {html_dump_path}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()