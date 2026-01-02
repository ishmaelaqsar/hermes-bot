# debug_bot.py
import os
import undetected_chromedriver as uc
import logging

logging.basicConfig(level=logging.DEBUG)

print("Starting debug test...")
options = uc.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")

print("Initializing driver...")
try:
    # Try to launch without a profile first to rule out permission errors
    chrome_ver = int(os.getenv("CHROME_VERSION", "143"))
    driver = uc.Chrome(options=options, version_main=chrome_ver)
    print("SUCCESS: Chrome launched!")
    driver.get("https://google.com")
    print("Page title:", driver.title)
    driver.quit()
except Exception as e:
    print(f"FAILED: {e}")
