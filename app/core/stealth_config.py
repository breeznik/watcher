from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import random
from pathlib import Path
import json
import yaml
import argparse
import os
from datetime import datetime, timedelta
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class FallbackStrategy(Enum):
    """Fallback strategies for content detection."""
    NONE = "none"
    OCR = "ocr"
    WAYBACK = "wayback"
    FUZZY_MATCH = "fuzzy_match"
    ALL = "all"

class RetryStrategy(Enum):
    """Retry strategies for failed checks."""
    NONE = "none"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR = "linear"
    SIZE_BASED = "size_based"

@dataclass
class UserAgentConfig:
    """Configuration for User-Agent rotation."""
    agents: List[str] = None
    weights: List[float] = None
    rotation_strategy: str = "random"

    def __post_init__(self):
        if self.agents is None:
            self.agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
            ]
        if self.weights is None:
            self.weights = [1.0] * len(self.agents)

    def get_random_agent(self) -> str:
        """Get a random User-Agent based on weights."""
        return random.choices(self.agents, weights=self.weights, k=1)[0]

@dataclass
class HeaderConfig:
    """Configuration for HTTP headers."""
    accept_language: str = "en-US,en;q=0.9"
    dnt: str = "1"
    referer: Optional[str] = None
    custom_headers: Dict[str, str] = None

@dataclass
class StealthConfig:
    """Configuration for stealth/anti-detection measures."""
    user_agents: UserAgentConfig = field(default_factory=UserAgentConfig)
    headers: HeaderConfig = field(default_factory=HeaderConfig)
    enable_webdriver_masking: bool = True
    enable_plugin_masking: bool = True
    enable_language_masking: bool = True
    enable_chrome_runtime: bool = True
    request_throttling: float = 0.0  # seconds between requests
    randomize_viewport: bool = True
    viewport_width_range: tuple = (1200, 1920)
    viewport_height_range: tuple = (700, 1080)

@dataclass
class RenderingConfig:
    """Configuration for smart rendering and interaction."""
    max_timeout: float = 90.0  # seconds (must be < 90s)
    poll_interval: float = 5.0  # seconds
    scroll_increment: int = 500  # pixels
    scroll_delay_range: tuple = (0.5, 2.0)  # seconds
    max_scrolls: int = 3
    hover_selectors: List[str] = None
    click_selectors: List[str] = None
    load_more_button_selectors: List[str] = None
    validate_visibility: bool = True

    def __post_init__(self):
        if self.hover_selectors is None:
            self.hover_selectors = [
                "button.load-more",
                "a.load-more",
                "div.load-more",
                ".infinite-scroll-trigger",
                "[data-load-more]"
            ]
        if self.click_selectors is None:
            self.click_selectors = [
                "button.load-more",
                "a.load-more",
                "div.load-more",
                ".show-more-button",
                "[data-click-load]"
            ]
        if self.load_more_button_selectors is None:
            self.load_more_button_selectors = [
                "button:has-text('Load More')",
                "button:has-text('Show More')",
                "button:has-text('See More')",
                "a:has-text('Load More')",
                "a:has-text('Show More')"
            ]

@dataclass
class SessionConfig:
    """Configuration for session and state persistence."""
    enable_cookie_storage: bool = True
    cookie_storage_path: str = "./data/cookies"
    cookie_expiration_days: int = 30
    session_ttl_seconds: int = 3600  # 1 hour
    max_sessions_per_domain: int = 5

@dataclass
class ResilienceConfig:
    """Configuration for resilience and fallback mechanisms."""
    max_retries: int = 3
    retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    backoff_base: float = 1.0  # seconds
    backoff_max: float = 5.0  # seconds
    size_threshold_percentage: float = 0.5  # retry if response < 50% of expected
    fallback_strategy: FallbackStrategy = FallbackStrategy.ALL
    ocr_enabled: bool = True
    wayback_enabled: bool = True
    fuzzy_match_enabled: bool = True
    fuzzy_match_threshold: int = 85  # Levenshtein similarity percentage

@dataclass
class MonitoringConfig:
    """Main configuration for the enhanced monitoring system."""
    stealth: StealthConfig = field(default_factory=StealthConfig)
    rendering: RenderingConfig = field(default_factory=RenderingConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
    debug_mode: bool = False
    log_level: str = "INFO"
    artifact_dir: str = "./data/artifacts"
    config_file: Optional[str] = None

def load_config_from_file(config_path: str) -> MonitoringConfig:
    """Load configuration from YAML or JSON file."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        if config_path.suffix in ('.yaml', '.yml'):
            config_data = yaml.safe_load(f)
        elif config_path.suffix == '.json':
            config_data = json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {config_path.suffix}")

    return parse_config_data(config_data)

def parse_config_data(config_data: Dict[str, Any]) -> MonitoringConfig:
    """Parse configuration data into MonitoringConfig object."""
    config = MonitoringConfig()

    # Parse stealth configuration
    if 'stealth' in config_data:
        stealth_data = config_data['stealth']
        if 'user_agents' in stealth_data:
            config.stealth.user_agents.agents = stealth_data['user_agents'].get('agents', config.stealth.user_agents.agents)
            config.stealth.user_agents.weights = stealth_data['user_agents'].get('weights', config.stealth.user_agents.weights)
            config.stealth.user_agents.rotation_strategy = stealth_data['user_agents'].get('rotation_strategy', config.stealth.user_agents.rotation_strategy)

        if 'headers' in stealth_data:
            headers_data = stealth_data['headers']
            config.stealth.headers.accept_language = headers_data.get('accept_language', config.stealth.headers.accept_language)
            config.stealth.headers.dnt = headers_data.get('dnt', config.stealth.headers.dnt)
            config.stealth.headers.referer = headers_data.get('referer', config.stealth.headers.referer)
            config.stealth.headers.custom_headers = headers_data.get('custom_headers', config.stealth.headers.custom_headers)

        # Parse boolean flags
        config.stealth.enable_webdriver_masking = stealth_data.get('enable_webdriver_masking', config.stealth.enable_webdriver_masking)
        config.stealth.enable_plugin_masking = stealth_data.get('enable_plugin_masking', config.stealth.enable_plugin_masking)
        config.stealth.enable_language_masking = stealth_data.get('enable_language_masking', config.stealth.enable_language_masking)
        config.stealth.enable_chrome_runtime = stealth_data.get('enable_chrome_runtime', config.stealth.enable_chrome_runtime)
        config.stealth.request_throttling = stealth_data.get('request_throttling', config.stealth.request_throttling)
        config.stealth.randomize_viewport = stealth_data.get('randomize_viewport', config.stealth.randomize_viewport)

    # Parse rendering configuration
    if 'rendering' in config_data:
        rendering_data = config_data['rendering']
        config.rendering.max_timeout = rendering_data.get('max_timeout', config.rendering.max_timeout)
        config.rendering.poll_interval = rendering_data.get('poll_interval', config.rendering.poll_interval)
        config.rendering.scroll_increment = rendering_data.get('scroll_increment', config.rendering.scroll_increment)
        config.rendering.max_scrolls = rendering_data.get('max_scrolls', config.rendering.max_scrolls)
        config.rendering.validate_visibility = rendering_data.get('validate_visibility', config.rendering.validate_visibility)

        # Parse selector lists
        if 'hover_selectors' in rendering_data:
            config.rendering.hover_selectors = rendering_data['hover_selectors']
        if 'click_selectors' in rendering_data:
            config.rendering.click_selectors = rendering_data['click_selectors']
        if 'load_more_button_selectors' in rendering_data:
            config.rendering.load_more_button_selectors = rendering_data['load_more_button_selectors']

    # Parse session configuration
    if 'session' in config_data:
        session_data = config_data['session']
        config.session.enable_cookie_storage = session_data.get('enable_cookie_storage', config.session.enable_cookie_storage)
        config.session.cookie_storage_path = session_data.get('cookie_storage_path', config.session.cookie_storage_path)
        config.session.cookie_expiration_days = session_data.get('cookie_expiration_days', config.session.cookie_expiration_days)
        config.session.session_ttl_seconds = session_data.get('session_ttl_seconds', config.session.session_ttl_seconds)
        config.session.max_sessions_per_domain = session_data.get('max_sessions_per_domain', config.session.max_sessions_per_domain)

    # Parse resilience configuration
    if 'resilience' in config_data:
        resilience_data = config_data['resilience']
        config.resilience.max_retries = resilience_data.get('max_retries', config.resilience.max_retries)
        config.resilience.retry_strategy = RetryStrategy(resilience_data.get('retry_strategy', config.resilience.retry_strategy.value))
        config.resilience.backoff_base = resilience_data.get('backoff_base', config.resilience.backoff_base)
        config.resilience.backoff_max = resilience_data.get('backoff_max', config.resilience.backoff_max)
        config.resilience.size_threshold_percentage = resilience_data.get('size_threshold_percentage', config.resilience.size_threshold_percentage)
        config.resilience.fallback_strategy = FallbackStrategy(resilience_data.get('fallback_strategy', config.resilience.fallback_strategy.value))
        config.resilience.ocr_enabled = resilience_data.get('ocr_enabled', config.resilience.ocr_enabled)
        config.resilience.wayback_enabled = resilience_data.get('wayback_enabled', config.resilience.wayback_enabled)
        config.resilience.fuzzy_match_enabled = resilience_data.get('fuzzy_match_enabled', config.resilience.fuzzy_match_enabled)
        config.resilience.fuzzy_match_threshold = resilience_data.get('fuzzy_match_threshold', config.resilience.fuzzy_match_threshold)

    # Parse general settings
    config.debug_mode = config_data.get('debug_mode', config.debug_mode)
    config.log_level = config_data.get('log_level', config.log_level)
    config.artifact_dir = config_data.get('artifact_dir', config.artifact_dir)

    return config

def parse_cli_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Enhanced Playwright Monitoring Script")

    # General options
    parser.add_argument("--url", help="URL to monitor")
    parser.add_argument("--selector", help="CSS selector to wait for")
    parser.add_argument("--phrase", help="Phrase to search for in page content")
    parser.add_argument("--timeout", type=float, default=90.0, help="Maximum timeout in seconds")
    parser.add_argument("--config", help="Path to YAML/JSON config file")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    # Stealth options
    parser.add_argument("--user-agent", help="Specific User-Agent to use")
    parser.add_argument("--no-stealth", action="store_true", help="Disable stealth measures")

    # Output options
    parser.add_argument("--output-dir", help="Directory for output artifacts")
    parser.add_argument("--screenshot", action="store_true", help="Take screenshots")
    parser.add_argument("--html-dump", action="store_true", help="Dump HTML content")

    return parser.parse_args()

def create_default_config_file(output_path: str = "app/core/monitoring_config.yaml"):
    """Create a default configuration file."""
    config = MonitoringConfig()

    config_dict = {
        "stealth": {
            "user_agents": {
                "agents": config.stealth.user_agents.agents,
                "weights": config.stealth.user_agents.weights,
                "rotation_strategy": config.stealth.user_agents.rotation_strategy
            },
            "headers": {
                "accept_language": config.stealth.headers.accept_language,
                "dnt": config.stealth.headers.dnt,
                "referer": config.stealth.headers.referer
            },
            "enable_webdriver_masking": config.stealth.enable_webdriver_masking,
            "enable_plugin_masking": config.stealth.enable_plugin_masking,
            "enable_language_masking": config.stealth.enable_language_masking,
            "enable_chrome_runtime": config.stealth.enable_chrome_runtime,
            "request_throttling": config.stealth.request_throttling,
            "randomize_viewport": config.stealth.randomize_viewport
        },
        "rendering": {
            "max_timeout": config.rendering.max_timeout,
            "poll_interval": config.rendering.poll_interval,
            "scroll_increment": config.rendering.scroll_increment,
            "max_scrolls": config.rendering.max_scrolls,
            "hover_selectors": config.rendering.hover_selectors,
            "click_selectors": config.rendering.click_selectors,
            "load_more_button_selectors": config.rendering.load_more_button_selectors,
            "validate_visibility": config.rendering.validate_visibility
        },
        "session": {
            "enable_cookie_storage": config.session.enable_cookie_storage,
            "cookie_storage_path": config.session.cookie_storage_path,
            "cookie_expiration_days": config.session.cookie_expiration_days,
            "session_ttl_seconds": config.session.session_ttl_seconds,
            "max_sessions_per_domain": config.session.max_sessions_per_domain
        },
        "resilience": {
            "max_retries": config.resilience.max_retries,
            "retry_strategy": config.resilience.retry_strategy.value,
            "backoff_base": config.resilience.backoff_base,
            "backoff_max": config.resilience.backoff_max,
            "size_threshold_percentage": config.resilience.size_threshold_percentage,
            "fallback_strategy": config.resilience.fallback_strategy.value,
            "ocr_enabled": config.resilience.ocr_enabled,
            "wayback_enabled": config.resilience.wayback_enabled,
            "fuzzy_match_enabled": config.resilience.fuzzy_match_enabled,
            "fuzzy_match_threshold": config.resilience.fuzzy_match_threshold
        },
        "debug_mode": config.debug_mode,
        "log_level": config.log_level,
        "artifact_dir": config.artifact_dir
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Created default config file: {output_path}")