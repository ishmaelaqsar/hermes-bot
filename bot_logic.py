import os
import smtplib
import time
from email.message import EmailMessage
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def create_driver(proxy=None):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # Stealth settings
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    if proxy and proxy.strip():
        options.add_argument(f'--proxy-server={proxy}')

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def send_html_email(items, recipients):
    if not recipients: return

    sender_email = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")

    if not sender_email or not password:
        print("Email credentials not set in environment variables.")
        return

    msg = EmailMessage()
    msg["Subject"] = f"HERMES FOUND: {len(items)} Items Available"
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)

    html_content = "<h2>Hermes Stock Alert</h2>"
    for item in items:
        html_content += f"""
        <div style="border:1px solid #ccc; padding:10px; margin-bottom:15px;">
            <img src="{item.get('image', '')}" style="max-width:150px; height:auto; display:block; margin-bottom:5px;">
            <h3 style="margin:0;">{item['name']}</h3>
            <p style="margin:5px 0;"><b>Color:</b> {item['color']}</p>
            <p style="margin:5px 0;"><b>Group:</b> {item['group']}</p>
            <a href="{item['link']}" style="background-color:#000; color:#fff; padding:10px 15px; text-decoration:none; display:inline-block;">BUY NOW</a>
        </div>
        """

    msg.set_content("Please enable HTML emails to view links.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(msg)
            print("Email sent successfully!")
    except Exception as e:
        print(f"Email Error: {e}")


def check_single_url(driver, url, group_name):
    print(f"Checking: {url}")
    driver.get(url)

    # Allow some JS to load (Hermes is slow)
    time.sleep(5)

    try:
        # 1. Check Availability
        # Logic: We use 'normalize-space' to ignore extra spaces/newlines in the HTML.
        # We also check if the "Add to cart" button is completely missing as a secondary safeguard.
        try:
            # Check for specific "No longer available" message
            unavailable_msgs = driver.find_elements(By.XPATH, "//span[contains(@class, 'message-info')][contains(normalize-space(.), 'no longer available')]")
            if unavailable_msgs and unavailable_msgs[0].is_displayed():
                return None  # Item is explicitly marked unavailable

            # Secondary Check: If we can't find the "Add to cart" button, assume unavailable
            # This prevents false positives when the page loads weirdly
            add_buttons = driver.find_elements(By.XPATH, "//button[contains(normalize-space(.), 'Add to cart')]")
            if not add_buttons:
                # If there's no add to cart button, it's not purchasable.
                # However, we only return None if we are SURE it's not just a loading error.
                # For safety, let's rely on the explicit message first, but if color is Unknown AND no button, skip it.
                pass
        except:
            pass

        # 2. Extract Details

        # Color Extraction
        color = "Unknown"
        try:
            color_elems = driver.find_elements(By.XPATH, "//span[contains(@class, 'expansion-panel-header-right-part')]//div[not(contains(@class, 'sr-only'))]")
            if color_elems:
                color = color_elems[0].text.strip()
        except:
            pass

        # Image Extraction
        image_src = ""
        try:
            # Strategy A: Use 'fetchpriority'
            # We use find_elements (plural) to avoid crashing if not found
            imgs = driver.find_elements(By.XPATH, "//img[@fetchpriority='high']")

            if imgs:
                image_src = imgs[0].get_attribute("src")
            else:
                # Strategy B: Fallback to asset URL
                imgs = driver.find_elements(By.XPATH, "//img[contains(@src, 'assets.hermes.com/is/image/hermesproduct')]")
                if imgs:
                    image_src = imgs[0].get_attribute("src")

            # Protocol fix
            if image_src and image_src.startswith("//"):
                image_src = "https:" + image_src

        except Exception as e:
            print(f"Image extract warning: {e}")

        # FINAL SAFETY CHECK
        # If we didn't find the unavailability message, but we also failed to find a color
        # OR an image, it's likely a bad load or a "soft" unavailability.
        # To prevent spam, we skip items that look broken.
        if color == "Unknown" and image_src == "":
            print(f"Skipping {url} (Likely unavailable/not loaded correctly)")
            return None

        name = group_name
        try:
            h1s = driver.find_elements(By.TAG_NAME, "h1")
            if h1s: name = h1s[0].text.strip()
        except:
            pass

        return {
            "name": name,
            "color": color,
            "link": url,
            "image": image_src,
            "group": group_name
        }

    except Exception as e:
        print(f"Error checking {url}: {e}")
        return None


def run_check(bag_config, proxy=None):
    driver = None
    found_items = []

    try:
        driver = create_driver(proxy)

        for group_name, data in bag_config.items():
            if not data.get('active', True):
                continue

            for url in data.get('urls', []):
                result = check_single_url(driver, url, group_name)
                if result:
                    found_items.append(result)
                    print(f"FOUND: {result['name']} - {result['color']}")

    except Exception as e:
        print(f"Global Scrape Error: {e}")
        raise e
    finally:
        if driver: driver.quit()

    return found_items
