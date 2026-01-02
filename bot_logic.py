import os
import smtplib
import time
import tempfile
import shutil
import random
import logging
from email.message import EmailMessage
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger(__name__)


class BotManager:
    """Manages persistent browser instance and anti-detection measures"""

    def __init__(self, proxy=None):
        self.proxy = proxy
        self.driver = None
        self.user_agents = [
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        ]
        self.current_user_agent = random.choice(self.user_agents)
        self._initialize_driver()

    def _initialize_driver(self):
        """Initialize the browser with anti-detection measures"""
        try:
            options = uc.ChromeOptions()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-setuid-sandbox")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("--dns-prefetch-disable")
            options.add_argument("--disable-ipv6")
            options.add_argument(f"user-agent={self.current_user_agent}")
            options.add_argument("--disable-features=ChromeWhatsNewUI")

            # Block heavy content
            prefs = {
                "profile.managed_default_content_settings.images": 2,
                "profile.managed_default_content_settings.fonts": 2,
                "profile.managed_default_content_settings.stylesheets": 1,  # Keep CSS
            }
            options.add_experimental_option("prefs", prefs)

            if self.proxy and self.proxy.strip():
                options.add_argument(f'--proxy-server={self.proxy}')

            chrome_ver = int(os.getenv("CHROME_VERSION", "143"))

            self.driver = uc.Chrome(
                options=options,
                version_main=chrome_ver,
                headless=False,
                use_subprocess=True
            )

            logger.info("Browser initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    def _human_like_delay(self, min_sec=1, max_sec=3):
        """Random delay to simulate human behavior"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def _random_mouse_movement(self):
        """Simulate random mouse movements"""
        try:
            actions = ActionChains(self.driver)
            for _ in range(random.randint(1, 3)):
                x = random.randint(100, 500)
                y = random.randint(100, 500)
                actions.move_by_offset(x, y)
            actions.perform()
        except Exception as e:
            logger.debug(f"Mouse movement skipped: {e}")

    def _random_scroll(self):
        """Simulate random scrolling behavior"""
        try:
            scroll_amount = random.randint(300, 800)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            self._human_like_delay(0.5, 1.5)

            # Sometimes scroll back up a bit
            if random.random() < 0.3:
                scroll_back = random.randint(100, 300)
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_back});")
                self._human_like_delay(0.3, 0.8)
        except Exception as e:
            logger.debug(f"Scroll simulation skipped: {e}")

    def _is_blocked(self, page_source=None):
        """Check if the page shows signs of being blocked"""
        if page_source is None:
            page_source = self.driver.page_source

        blocked_indicators = [
            "captcha-delivery.com",
            "DataDome",
            "Access Denied",
            "blocked",
            "checking your browser",
            "Please verify you are a human"
        ]

        source_lower = page_source.lower()
        for indicator in blocked_indicators:
            if indicator.lower() in source_lower:
                logger.warning(f"Blocking detected: {indicator}")
                return True

        return False

    def check_single_url(self, url, group_name):
        """Check a single URL for availability with anti-detection measures"""
        logger.info(f"Checking: {url}")

        try:
            # Random delay before request
            self._human_like_delay(2, 5)

            # Load the page
            self.driver.get(url)

            # Initial wait for page to start loading
            time.sleep(2)

            # Check for blocking immediately
            if self._is_blocked():
                logger.error(f"❌ BLOCKED: Anti-bot detected for {url}")
                return None, True  # Return blocked flag

            # Simulate human behavior
            self._random_scroll()
            self._human_like_delay(1, 2)

            # Wait for content to load with random variation
            wait_time = random.uniform(3, 6)
            time.sleep(wait_time)

            # Check again for late-loading blocks
            if self._is_blocked():
                logger.error(f"❌ BLOCKED: Late anti-bot detection for {url}")
                return None, True

            # Check availability
            unavailable = self._check_unavailability()
            if unavailable:
                logger.info(f"Item unavailable: {url}")
                return None, False

            # Extract product details
            details = self._extract_product_details(url, group_name)

            if details:
                logger.info(f"✓ FOUND: {details['name']} - {details['color']}")
                return details, False
            else:
                logger.info(f"Could not extract details for {url}")
                return None, False

        except Exception as e:
            logger.error(f"Error checking {url}: {e}")
            # Check if error is due to blocking
            try:
                if self._is_blocked():
                    return None, True
            except:
                pass
            return None, False

    def _check_unavailability(self):
        """Check if item is unavailable using multiple strategies"""
        try:
            # Strategy 1: Explicit unavailability message
            unavailable_msgs = self.driver.find_elements(
                By.XPATH,
                "//span[contains(@class, 'message-info')][contains(normalize-space(.), 'no longer available')]"
            )
            if unavailable_msgs and any(msg.is_displayed() for msg in unavailable_msgs):
                return True

            # Strategy 2: Check for "Add to cart" button
            add_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(normalize-space(.), 'Add to cart') or contains(normalize-space(.), 'Add to bag')]"
            )

            # If button exists and is enabled, item is available
            if add_buttons:
                for btn in add_buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        return False  # Available!

            # Strategy 3: Look for sold out indicators
            sold_out_indicators = self.driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'sold out') or contains(text(), 'Sold Out') or contains(text(), 'out of stock')]"
            )
            if sold_out_indicators:
                return True

            # If no clear availability signal, assume unavailable to avoid false positives
            return True

        except Exception as e:
            logger.debug(f"Availability check error: {e}")
            return True  # Assume unavailable on error

    def _extract_product_details(self, url, group_name):
        """Extract product details from the page"""
        try:
            # Extract color
            color = "Unknown"
            try:
                color_elems = self.driver.find_elements(
                    By.XPATH,
                    "//span[contains(@class, 'expansion-panel-header-right-part')]//div[not(contains(@class, 'sr-only'))]"
                )
                if color_elems:
                    color = color_elems[0].text.strip()

                # Fallback color extraction
                if not color or color == "Unknown":
                    color_elems = self.driver.find_elements(
                        By.XPATH,
                        "//*[contains(@class, 'color') or contains(@class, 'Color')]//span"
                    )
                    if color_elems:
                        color = color_elems[0].text.strip()
            except Exception as e:
                logger.debug(f"Color extraction error: {e}")

            # Extract image
            image_src = ""
            try:
                # Strategy A: High priority image
                imgs = self.driver.find_elements(By.XPATH, "//img[@fetchpriority='high']")
                if imgs:
                    image_src = imgs[0].get_attribute("src")

                # Strategy B: Hermes asset URL
                if not image_src:
                    imgs = self.driver.find_elements(
                        By.XPATH,
                        "//img[contains(@src, 'assets.hermes.com/is/image/hermesproduct')]"
                    )
                    if imgs:
                        image_src = imgs[0].get_attribute("src")

                # Strategy C: Any product image
                if not image_src:
                    imgs = self.driver.find_elements(
                        By.XPATH,
                        "//img[contains(@alt, 'product') or contains(@class, 'product')]"
                    )
                    if imgs:
                        image_src = imgs[0].get_attribute("src")

                # Fix protocol
                if image_src and image_src.startswith("//"):
                    image_src = "https:" + image_src

            except Exception as e:
                logger.debug(f"Image extraction error: {e}")

            # Extract name
            name = group_name
            try:
                h1s = self.driver.find_elements(By.TAG_NAME, "h1")
                if h1s:
                    name = h1s[0].text.strip()

                # Fallback to title
                if not name or name == group_name:
                    name = self.driver.title.split('|')[0].strip()
            except Exception as e:
                logger.debug(f"Name extraction error: {e}")

            # Quality check: Need at least name and one other field
            if name and (color != "Unknown" or image_src):
                return {
                    "name": name,
                    "color": color,
                    "link": url,
                    "image": image_src,
                    "group": group_name
                }

            logger.debug("Insufficient data extracted")
            return None

        except Exception as e:
            logger.error(f"Product detail extraction error: {e}")
            return None

    def run_check(self, bag_config):
        """Run check across all configured bags"""
        found_items = []
        was_blocked = False

        try:
            # Ensure driver is initialized
            if self.driver is None:
                self._initialize_driver()

            active_groups = [(name, data) for name, data in bag_config.items()
                           if data.get('active', True)]

            if not active_groups:
                logger.info("No active groups to check")
                return found_items, was_blocked

            logger.info(f"Checking {len(active_groups)} active groups")

            # Shuffle groups to vary order
            random.shuffle(active_groups)

            for group_name, data in active_groups:
                urls = data.get('urls', [])
                if not urls:
                    continue

                # Shuffle URLs within group
                urls_copy = urls.copy()
                random.shuffle(urls_copy)

                for url in urls_copy:
                    result, blocked = self.check_single_url(url, group_name)

                    if blocked:
                        was_blocked = True
                        logger.warning("Blocking detected, stopping check cycle")
                        return found_items, was_blocked

                    if result:
                        found_items.append(result)

                    # Random delay between URLs
                    if urls_copy.index(url) < len(urls_copy) - 1:
                        delay = random.uniform(3, 8)
                        logger.debug(f"Waiting {delay:.1f}s before next URL")
                        time.sleep(delay)

                # Delay between groups
                if active_groups.index((group_name, data)) < len(active_groups) - 1:
                    delay = random.uniform(5, 12)
                    logger.debug(f"Waiting {delay:.1f}s before next group")
                    time.sleep(delay)

            logger.info(f"Check cycle completed. Found: {len(found_items)}, Blocked: {was_blocked}")

        except Exception as e:
            logger.error(f"Run check error: {e}", exc_info=True)
            # Try to detect if error was due to blocking
            try:
                if self.driver and self._is_blocked():
                    was_blocked = True
            except:
                pass

        return found_items, was_blocked

    def cleanup(self):
        """Clean up browser resources"""
        if self.driver:
            profile_path = None
            # Extract profile path from options before quitting
            for arg in self.driver.options.arguments:
                if arg.startswith("user-data-dir="):
                    profile_path = arg.split("=", 1)[1]
                    break

            try:
                logger.info("Closing browser")
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
            finally:
                self.driver = None

            # Remove temp profile
            if profile_path and os.path.exists(profile_path):
                try:
                    shutil.rmtree(profile_path)
                except:
                    pass


def send_html_email(items, recipients):
    """Send HTML email notification with found items"""
    if not recipients:
        logger.warning("No recipients specified for email")
        return

    sender_email = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")

    if not sender_email or not password:
        logger.error("Email credentials not set in environment variables")
        return

    msg = EmailMessage()
    msg["Subject"] = f"🚨 HERMES ALERT: {len(items)} Items Available!"
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)

    html_content = """
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333; border-bottom: 2px solid #000; padding-bottom: 10px;">
            🛍️ Hermes Stock Alert
        </h2>
        <p style="color: #666; font-size: 14px;">
            The following items are now available. Act fast!
        </p>
    """

    for item in items:
        html_content += f"""
        <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin-bottom: 20px; background-color: #f9f9f9;">
            {f'<img src="{item.get("image", "")}" style="max-width: 200px; height: auto; display: block; margin-bottom: 10px; border-radius: 4px;">' if item.get('image') else ''}
            <h3 style="margin: 0 0 10px 0; color: #000;">{item['name']}</h3>
            <p style="margin: 5px 0; color: #666;"><strong>Color:</strong> {item['color']}</p>
            <p style="margin: 5px 0; color: #666;"><strong>Group:</strong> {item['group']}</p>
            <a href="{item['link']}" style="display: inline-block; background-color: #000; color: #fff; padding: 12px 24px; text-decoration: none; border-radius: 4px; margin-top: 10px; font-weight: bold;">
                BUY NOW →
            </a>
        </div>
        """

    html_content += """
        <p style="color: #999; font-size: 12px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
            This is an automated notification from your Hermes monitoring bot.
        </p>
    </div>
    """

    msg.set_content("Please enable HTML emails to view this message properly.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(msg)
            logger.info(f"Email sent successfully to {len(recipients)} recipients")
    except Exception as e:
        logger.error(f"Email send error: {e}")
