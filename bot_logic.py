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


# Specific URL for Hermes UK Bags
URL = "https://www.hermes.com/uk/en/category/women/bags-and-small-leather-goods/bags-and-clutches/#fh_view_size=48&country=uk&fh_refpath=84b794f4-a6bd-48ff-9f38-c1a7b60d5a50&fh_refview=lister&fh_reffacet=display_state_uk&fh_location=%2f%2fcatalog01%2fen_US%2fis_visible%3e%7buk%7d%2fis_searchable%3e%7buk%7d%2fis_sellable%3e%7buk%7d%2fhas_stock%3e%7buk%7d%2fitem_type%3dproduct%2fcategories%3c%7bcatalog01_women_womenbagssmallleathergoods_womenbagsbagsclutches%7d%2fobject_type_filter%3e%7bsacs_a_main%3bsacs_bandouliere%3bcabas%3bpochettes%7d%2fdisplay_state_uk%3e%7becom%3becom_display%3bdisplay%7d|"


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-data-dir={os.getcwd()}/chrome_profile")
    options.binary_location = "/usr/bin/chromium"

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--window-size=1920,1080")

    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=options)


def send_html_email(items, recipients):
    if not recipients: return

    email = os.environ.get("GMAIL_ADDRESS")

    msg = EmailMessage()
    msg["Subject"] = f"HERMES ALERT: {len(items)} Items Available"
    msg["From"] = email
    msg["To"] = ", ".join(recipients)

    # HTML Email with Images
    html_content = "<h2>Hermes Stock Alert</h2>"
    for item in items:
        html_content += f"""
        <div style="border:1px solid #ddd; padding:10px; margin-bottom:10px;">
            <img src="{item['image']}" width="100" style="float:left; margin-right:10px;">
            <p><b>{item['name']}</b></p>
            <p>Price: {item['price']}</p>
            <p><a href="{item['link']}">Buy Now</a></p>
            <div style="clear:both;"></div>
        </div>
        """

    msg.set_content("Please enable HTML emails to view links.")
    msg.add_alternative(html_content, subtype='html')

    try:
        password = os.environ.get("GMAIL_APP_PASSWORD")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email, password)
            server.send_message(msg)
    except Exception as e:
        print(f"Email Error: {e}")


def run_check(ignore_list):
    driver = None
    found_items = []

    try:
        driver = create_driver()
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

                # Get Image URL (New Logic)
                try:
                    # Look for the first image tag inside the product card
                    img_elem = product.find_element(By.TAG_NAME, "img")
                    image_url = img_elem.get_attribute("src")

                    # Sometimes src is lazy-loaded, check 'data-src' if needed
                    if not image_url or "base64" in image_url:
                        image_url = img_elem.get_attribute("data-src")

                    # Fix relative URLs if any
                    if image_url and image_url.startswith("//"):
                        image_url = "https:" + image_url
                except:
                    image_url = "https://via.placeholder.com/150?text=No+Image"

                found_items.append({
                    "name": text[:60] + "...",
                    "full_text": text,
                    "price": "Check Link",
                    "link": link,
                    "image": image_url  # Add to data dictionary
                })

            except StaleElementReferenceException:
                continue

    except Exception as e:
        print(f"Scrape Error: {e}")
    finally:
        if driver: driver.quit()

    return found_items
