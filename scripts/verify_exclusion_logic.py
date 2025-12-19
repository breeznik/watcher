
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
    'div:has(h3:has-text("Overview")), '
    'div[class*="Itemstyled__Item"]:has(:text("Sold out")), '
    'div[class*="Itemstyled__Item"]:has(:text("Sold Out")), '
    'div:has-text("Sold out"), '
    'div:has-text("sold out"), '
    '[class*="soldout"], '
    '[class*="unavailable"], '
    '[class*="sold-out"], '
    '[class*="out-of-stock"], '
    'div:has-text("Unavailable")'
)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    print("Navigating...")
    page.goto(url, timeout=60000)
    time.sleep(5) # Wait for load
    
    # Run exclusion
    print("Removing elements...")
    page.locator(exclude_selector).evaluate_all("els => els.forEach(el => el.remove())")
    
    content = page.content()
    if "Superior Twin" in content:
        print("Still FOUND 'Superior Twin'")
        # context
        idx = content.find("Superior Twin")
        print(content[idx-200:idx+200])
    else:
        print("NOT FOUND 'Superior Twin' (Exclusion successful)")
    
    browser.close()
