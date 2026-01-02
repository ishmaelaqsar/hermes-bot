import os
import smtplib
import time
import tempfile
import shutil
import random
import logging
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Optional, Dict, List, Tuple, Any

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

# Setup module logger
logger = logging.getLogger(__name__)

class BotManager:
    """Manages persistent browser instance and anti-detection measures."""

    def __init__(self, proxy: str = None):
        self.proxy = proxy
        self.driver = None
        self.profile_path = None

        # User Agents matching Chrome 143 (Server Version)
        self.user_agents = [
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        ]
        self.current_user_agent = random.choice(self.user_agents)
        self._initialize_driver()

    def _initialize_driver(self):
        """Initialize Chrome with robust anti-detection settings."""
        try:
            options = uc.ChromeOptions()

            # -------------------------------------------------
            # 1. PROFILE & DIRECTORY MANAGEMENT
            # -------------------------------------------------
            self.profile_path = tempfile.mkdtemp(prefix="hermes_bot_")
            options.add_argument(f"--user-data-dir={self.profile_path}")

            # -------------------------------------------------
            # 2. NETWORK & SECURITY FLAGS
            # -------------------------------------------------
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-setuid-sandbox")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=IsolateOrigins,site-per-process")
            options.add_argument("--disable-blink-features=AutomationControlled")

            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("--dns-prefetch-disable")
            options.add_argument("--disable-ipv6")

            # -------------------------------------------------
            # 3. FINGERPRINTING & STEALTH
            # -------------------------------------------------
            w = random.choice([1366, 1440, 1920])
            h = random.choice([768, 900, 1080])
            options.add_argument(f"--window-size={w},{h}")

            options.add_argument("--lang=en-GB")
            self.current_user_agent = random.choice(self.user_agents)
            options.add_argument(f"user-agent={self.current_user_agent}")

            if self.proxy and self.proxy.strip():
                options.add_argument(f'--proxy-server={self.proxy}')

            prefs = {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.default_content_setting_values.notifications": 2,
                "intl.accept_languages": "en-GB,en-US;q=0.9,en;q=0.8",
            }
            options.add_experimental_option("prefs", prefs)

            # -------------------------------------------------
            # 4. INITIALIZATION
            # -------------------------------------------------
            chrome_ver = int(os.getenv("CHROME_VERSION", "143"))
            logger.info(f"Starting Chrome {chrome_ver} with profile {self.profile_path}...")

            self.driver = uc.Chrome(
                options=options,
                version_main=chrome_ver,
                headless=False,
                use_subprocess=True,
                driver_executable_path=None
            )

            self._apply_stealth_scripts()
            logger.info("Browser initialized successfully.")

        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            self.cleanup()
            raise

    def _apply_stealth_scripts(self):
        """Apply JavaScript patches."""
        stealth_scripts = """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
        """
        try:
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': stealth_scripts
            })
        except Exception as e:
            logger.debug(f"Stealth script injection failed: {e}")

    def _human_like_delay(self, min_sec=2.0, max_sec=5.0):
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def _random_scroll(self):
        try:
            scroll_amount = random.randint(300, 700)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            logger.debug(f"Scroll failed: {e}")

    def _is_blocked(self, page_source=None) -> bool:
        try:
            if not page_source:
                page_source = self.driver.page_source

            blocked_keywords = [
                "captcha-delivery.com", "datadome", "access denied",
                "verify you are a human", "security check"
            ]

            if any(k in self.driver.title.lower() for k in ["blocked", "security", "captcha"]):
                return True
            if "captcha" in self.driver.current_url.lower():
                return True

            source_lower = page_source.lower()
            return any(k in source_lower for k in blocked_keywords)

        except Exception:
            return True

    def _check_unavailability(self) -> bool:
        try:
            buttons = self.driver.find_elements(By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add to cart')]")
            if buttons:
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        return False

            text_indicators = ["sold out", "out of stock", "no longer available"]
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(i in page_text for i in text_indicators):
                return True

            return True
        except Exception:
            return True

    def _extract_product_details(self, url: str, group_name: str) -> Optional[Dict]:
        try:
            name = group_name
            try:
                h1 = self.driver.find_element(By.TAG_NAME, "h1")
                name = h1.text.strip()
            except:
                pass

            color = "Unknown"
            try:
                elements = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'color') or contains(@class, 'Color')]//span")
                if elements:
                    color = elements[0].text.strip()
            except:
                pass

            image = ""
            try:
                imgs = self.driver.find_elements(By.XPATH, "//img[contains(@src, 'assets.hermes.com')]")
                if imgs:
                    image = imgs[0].get_attribute("src")
                    if image.startswith("//"):
                        image = "https:" + image
            except:
                pass

            return {
                "name": name,
                "color": color,
                "link": url,
                "image": image,
                "group": group_name
            }
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return None

    def check_single_url(self, url: str, group_name: str) -> Tuple[Optional[Dict], bool]:
        """
        Check a single URL.
        Returns: (ProductDetails, IsBlocked)
        """
        logger.info(f"Checking: {url}")
        try:
            self.driver.get(url)
            self._human_like_delay(3, 6)

            if self._is_blocked():
                logger.error(f"❌ BLOCKED: {url}")
                return None, True

            self._random_scroll()

            if self._check_unavailability():
                logger.info(f"Item unavailable: {url}")
                return None, False

            details = self._extract_product_details(url, group_name)
            if details:
                logger.info(f"✓ FOUND: {details['name']}")
                return details, False

            return None, False

        except Exception as e:
            logger.error(f"Error checking {url}: {e}")
            return None, False

    def run_check(self, bag_config: Dict, blacklist: Dict[str, str] = {}) -> Tuple[List[Dict], bool, Optional[str]]:
        """
        Main entry point to check all groups.
        Args:
            bag_config: Config for bags
            blacklist: Dictionary of {url: timestamp_string}
        Returns:
            (found_items, was_blocked, culprit_url)
        """
        found_items = []
        was_blocked = False
        culprit_url = None

        if not self.driver:
            self._initialize_driver()

        try:
            groups = [(k, v) for k, v in bag_config.items() if v.get('active', True)]
            random.shuffle(groups)

            for group_name, data in groups:
                urls = data.get('urls', [])
                random.shuffle(urls)

                for url in urls:
                    # --- Blacklist Check ---
                    if url in blacklist:
                        try:
                            blocked_time = datetime.fromisoformat(blacklist[url])
                            if datetime.now() - blocked_time < timedelta(hours=24):
                                logger.info(f"⏭️ Skipping blacklisted URL (Time remaining): {url}")
                                continue
                            else:
                                logger.info(f"Blacklist expired for: {url}")
                                # We don't modify the dict here, app.py handles cleanup
                        except ValueError:
                            pass # Invalid date format, try anyway

                    # --- Perform Check ---
                    details, blocked = self.check_single_url(url, group_name)

                    if blocked:
                        # Return immediately, identifying the URL that caused it
                        return found_items, True, url

                    if details:
                        found_items.append(details)

                    self._human_like_delay(5, 10)

                self._human_like_delay(10, 20)

        except Exception as e:
            logger.error(f"Run loop error: {e}")
            try:
                if self._is_blocked():
                    was_blocked = True
                    # If we crashed and are blocked, we might not know exactly which URL,
                    # but usually it's the current one. For safety, we just return blocked status.
            except:
                pass

        return found_items, was_blocked, culprit_url

    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            time.sleep(1.5)

        if self.profile_path and os.path.exists(self.profile_path):
            try:
                shutil.rmtree(self.profile_path, ignore_errors=True)
                logger.info(f"Cleaned up profile: {self.profile_path}")
            except Exception as e:
                logger.error(f"Failed to delete profile {self.profile_path}: {e}")
        self.profile_path = None

# -------------------------------------------------------------------------
# Standalone Functions
# -------------------------------------------------------------------------

def send_html_email(items: List[Dict], recipients: List[str]):
    """Send email notification."""
    if not recipients or not items:
        return

    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")

    if not sender or not password:
        logger.error("Email credentials missing.")
        return

    msg = EmailMessage()
    msg["Subject"] = f"🚨 HERMES FOUND: {len(items)} Items!"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    html_body = """
    <div style='font-family: sans-serif; max-width: 600px; margin: auto;'>
        <h2 style='border-bottom: 2px solid black;'>🛍️ Stock Alert</h2>
    """

    for item in items:
        html_body += f"""
        <div style='border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; border-radius: 5px;'>
            <h3>{item['name']}</h3>
            <p><strong>Color:</strong> {item['color']}</p>
            <p><a href="{item['link']}" style='background: black; color: white; padding: 10px; text-decoration: none; display: inline-block; border-radius: 4px;'>BUY NOW</a></p>
            {f'<img src="{item["image"]}" width="150"><br>' if item["image"] else ''}
        </div>
        """

    html_body += "</div>"
    msg.set_content("Enable HTML to view items.")
    msg.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        logger.info(f"Email sent to {len(recipients)} recipients.")
    except Exception as e:
        logger.error(f"Email failed: {e}")
