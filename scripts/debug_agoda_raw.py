
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.enhanced_monitor import EnhancedMonitor
from app.core.stealth_config import MonitoringConfig

def run_debug():
    # Setup config to dump artifacts
    config = MonitoringConfig()
    config.debug_mode = True
    config.artifact_dir = "./data/artifacts_debug"
    
    monitor = EnhancedMonitor(config)
    
    url = "https://www.agoda.com/en-gb/just-palace/hotel/taipei-tw.html?checkin=2026-06-12&checkout=2026-06-17&los=5&rooms=1&adults=2&children=0&cid=1836651&searchrequestid=71ecd0d0-ec13-41e9-b154-c3f7bb463083&af_sub3=01d44994-c644-4a4e-bf94-f555f9a0aede&af_sub4=cgt4gpsxcak45p5zhxnzef2c&priceView=3&currencyCode=USD"
    target_phrase = "Deluxe Quadruple"
    
    # Comprehensive selector matching watcher_service.py
    exclude_selector = (
        'div[data-testid="soldout-room-offer"], '
        'script, style, noscript, nav, footer, '
        '[class*="Review"], '
        '[class*="PropertyGallery"], '
        'option, '
        'div:has(h3:has-text("About")), '
        'div:has(h3:has-text("Overview")), '
        'div[class*="Itemstyled__Item"]:has(:text("Sold out")), '
        'div[class*="Itemstyled__Item"]:has(:text("Sold Out"))'
    )
    
    print(f"Monitoring {url}...")
    found, msg, metrics = monitor.monitor_url(
        url=url,
        target_phrase=target_phrase,
        exclude_selector=exclude_selector,
        screenshot_path=f"{config.artifact_dir}/debug_screenshot.png",
        html_dump_path=f"{config.artifact_dir}/debug_content.html"
    )
    
    print(f"Found: {found}")
    print(f"Message: {msg}")
    print(f"Artifacts saved to {config.artifact_dir}")

if __name__ == "__main__":
    run_debug()
