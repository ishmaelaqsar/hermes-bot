import os
import smtplib
from email.message import EmailMessage
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager


# Hermes UK Bags URL
URL = "https://www.hermes.com/uk/en/category/women/bags-and-small-leather-goods/bags-and-clutches/#fh_view_size=48&country=uk&fh_refpath=5134e23c-83df-4ccc-9c1e-58e00f7e4bfd&fh_refview=lister&fh_reffacet=object_type_filter&fh_location=%2f%2fcatalog01%2fen_US%2fis_visible%3e%7buk%7d%2fis_searchable%3e%7buk%7d%2fis_sellable%3e%7buk%7d%2fhas_stock%3e%7buk%7d%2fitem_type%3dproduct%2fcategories%3c%7bcatalog01_women_womenbagssmallleathergoods_womenbagsbagsclutches%7d%2fdisplay_state_uk%3e%7becom%3becom_display%7d%2fobject_type_filter%3e%7bsacs_bandouliere%3bpochettes%7d|"

def create_driver(proxy=None):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # Block images to save data (User Request)
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.images": 2
    }
    options.add_experimental_option("prefs", prefs)
    # -----------------------

    # Stealth settings
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # --- PROXY CONFIGURATION ---
    if proxy and proxy.strip():
        print(f"Using Proxy: {proxy}")
        options.add_argument(f'--proxy-server={proxy}')
    # ---------------------------

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def send_html_email(items, recipients):
    if not recipients: return

    sender_email = os.environ.get("GMAIL_ADDRESS")

    msg = EmailMessage()
    msg["Subject"] = f"HERMES ALERT: {len(items)} Items Available"
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)

    # Simplified HTML Email (Text Links Only)
    html_content = "<h2>Hermes Stock Alert</h2><ul>"
    for item in items:
        html_content += f"""
        <li style="margin-bottom: 15px;">
            <b>{item['name']}</b><br>
            Price: {item['price']}<br>
            <a href="{item['link']}">Buy Now</a>
        </li>
        """
    html_content += "</ul>"

    msg.set_content("Please enable HTML emails to view links.")
    msg.add_alternative(html_content, subtype='html')

    try:
        password = os.environ.get("GMAIL_APP_PASSWORD")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.send_message(msg)
    except Exception as e:
        print(f"Email Error: {e}")


def run_check(ignore_list, proxy=None):
    driver = None
    found_items = []

    try:
        driver = create_driver(proxy)
        driver.get(URL)
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'product-item')] | //body")))

        products = driver.find_elements(By.XPATH, "//div[contains(@class, 'product-item')]")
        if not products:
            products = driver.find_elements(By.XPATH, "//li[contains(@class, 'grid-item')]")

        for product in products:
            try:
                text = product.text.replace("\n", " ")
                clean_text = text.lower()

                # Filters
                if "unavailable" in clean_text: continue
                if "bag" not in clean_text and "clutch" not in clean_text: continue
                if any(ignore_word.lower() in clean_text for ignore_word in ignore_list): continue

                # Get Link
                try:
                    link_elem = product.find_element(By.TAG_NAME, "a")
                    link = link_elem.get_attribute("href")
                except:
                    link = URL

                # Note: Image scraping removed to save complexity/bandwidth

                found_items.append({
                    "name": text[:60] + "...",
                    "full_text": text,
                    "price": "Check Link",
                    "link": link
                })

            except StaleElementReferenceException:
                continue

    except Exception as e:
        print(f"Scrape Error: {e}")
        # Re-raise exception so app.py knows it failed
        raise e
    finally:
        if driver: driver.quit()

    return found_items
