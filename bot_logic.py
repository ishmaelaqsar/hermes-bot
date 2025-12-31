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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.send_message(msg)
    except Exception as e:
        print(f"Email Error: {e}")


def check_single_url(driver, url, group_name):
    print(f"Checking: {url}")
    driver.get(url)

    # Allow some JS to load
    time.sleep(3)

    try:
        # 1. Check Availability
        # Logic: If the "Unavailable" message exists, the bag is NOT available.
        try:
            unavailable_msg = driver.find_element(By.XPATH, "//span[contains(@class, 'message-info') and contains(text(), 'no longer available')]")
            if unavailable_msg.is_displayed():
                return None # Item is unavailable
        except:
            pass

        # 2. Extract Details (If we passed the unavailability check)

        # Color Extraction
        color = "Unknown"
        try:
            color_elem = driver.find_element(By.XPATH, "//span[contains(@class, 'expansion-panel-header-right-part')]//div[not(contains(@class, 'sr-only'))]")
            color = color_elem.text.strip()
        except:
            pass

        image_src = ""
        try:
            # We try multiple strategies to find the best image
            # Strategy A: Look for the specific 'fetchpriority' attribute seen in your snippet
            img_elem = driver.find_element(By.XPATH, "//img[@fetchpriority='high']")

            # Strategy B (Fallback): Look for any image coming from the Hermes product asset URL
            if not img_elem:
                img_elem = driver.find_element(By.XPATH, "//img[contains(@src, 'assets.hermes.com/is/image/hermesproduct')]")

            image_src = img_elem.get_attribute("src")

            # Fix protocol-relative URLs (if the browser returns //assets...)
            if image_src.startswith("//"):
                image_src = "https:" + image_src

        except Exception as e:
            print(f"Image extract warning: {e}")
            # Fallback to a placeholder or empty string if no image found
            image_src = ""

        name = group_name # Default to group name
        try:
            name = driver.find_element(By.TAG_NAME, "h1").text.strip()
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
    """
    bag_config: The 'bags' dictionary from config.json
    """
    driver = None
    found_items = []

    try:
        driver = create_driver(proxy)

        for group_name, data in bag_config.items():
            # Skip if bag group is unchecked/inactive
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
