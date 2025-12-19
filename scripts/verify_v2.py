
import os
from playwright.sync_api import sync_playwright
import time

url = "https://www.agoda.com/en-gb/just-palace/hotel/taipei-tw.html?checkin=2026-06-12&checkout=2026-06-17&los=5&rooms=1&adults=2&children=0&cid=1836651&searchrequestid=71ecd0d0-ec13-41e9-b154-c3f7bb463083&af_sub3=01d44994-c644-4a4e-bf94-f555f9a0aede&af_sub4=cgt4gpsxcak45p5zhxnzef2c&priceView=3&currencyCode=USD"

exclude_selector = (
    'div[data-testid="soldout-room-offer"], '
    'script, style, noscript, nav, footer, '
    '[class*="Review"], '
    '[class*="PropertyGallery"], '
    'option, '
    'div:has(h3:has-text("About")), '
    'div:has(h3:has-text("Overview"))'
)

print("Starting verification...")
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    print("Navigating...")
    page.goto(url)
    print("Waiting for load...")
    time.sleep(10)
    
    print("Applying exclusion...")
    try:
        page.locator(exclude_selector).evaluate_all("els => els.forEach(el => el.remove())")
        print("Exclusion applied.")
    except Exception as e:
        print(f"Exclusion failed: {e}")

    content = page.content()
    if "Deluxe Quadruple" in content:
        print("FOUND: Deluxe Quadruple is still present.")
    else:
        print("NOT FOUND: Deluxe Quadruple successfully removed.")
        
    browser.close()
