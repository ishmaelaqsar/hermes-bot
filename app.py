import atexit
import datetime
import json
import logging
import os
import random
import threading
import time
from typing import Dict, Any, List, Optional

from flask import Flask, render_template, request, redirect, url_for
from pyvirtualdisplay import Display

# Local imports
from bot_logic import BotManager, send_html_email

# -------------------------------------------------------------------------
# Logging Setup
# -------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Application Configuration
# -------------------------------------------------------------------------
app = Flask(__name__)
CONFIG_FILE = 'config.json'

DEFAULT_CONFIG = {
    "bags": {},
    "emails": [],
    "min_interval_minutes": 20,
    "max_interval_minutes": 40,
    "proxy": "",
    "blocked_count": 0,
    "success_count": 0,
    "last_blocked_time": None,
    "last_run_status": "Waiting to start..."
}

# Global State
bot_manager: Optional[BotManager] = None
virtual_display: Optional[Display] = None


# -------------------------------------------------------------------------
# Display Management (Xvfb)
# -------------------------------------------------------------------------
def start_display():
    """Start the virtual display (Xvfb) for headless Chrome."""
    global virtual_display
    try:
        logger.info("Starting virtual display...")
        virtual_display = Display(visible=0, size=(1920, 1080))
        virtual_display.start()
        logger.info("Virtual display started successfully.")
    except Exception as e:
        logger.error(f"Failed to start virtual display: {e}")

def stop_display():
    """Stop the virtual display on exit."""
    global virtual_display
    if virtual_display:
        try:
            logger.info("Stopping virtual display...")
            virtual_display.stop()
        except Exception as e:
            logger.error(f"Error stopping display: {e}")

atexit.register(stop_display)


# -------------------------------------------------------------------------
# Config Management
# -------------------------------------------------------------------------
def load_config() -> Dict[str, Any]:
    """Load configuration with safe fallback to defaults."""
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            # Merge with defaults to ensure all keys exist
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            return config
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error loading config: {e}. Using defaults.")
        return DEFAULT_CONFIG.copy()

def save_config(data: Dict[str, Any]):
    """Save configuration to disk."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


# -------------------------------------------------------------------------
# Background Worker Logic
# -------------------------------------------------------------------------
def calculate_backoff_delay(blocked_count: int) -> int:
    """Calculate exponential backoff delay in seconds."""
    if blocked_count <= 0:
        return 0

    # Exponential: 5m, 10m, 20m, 40m, 80m, capped at 2 hours
    base_minutes = 5
    backoff_minutes = min(base_minutes * (2 ** (blocked_count - 1)), 120)

    # Add +/- 20% jitter
    jitter = random.uniform(0.8, 1.2)
    return int(backoff_minutes * 60 * jitter)

def background_worker():
    """Main background loop for checking stock."""
    global bot_manager
    logger.info("Background worker started")
    consecutive_errors = 0

    while True:
        config = load_config()

        try:
            # 1. Handle Blocking / Backoff
            blocked_count = config.get('blocked_count', 0)
            if blocked_count > 0:
                delay = calculate_backoff_delay(blocked_count)
                logger.warning(f"⚠️ Backing off for {delay // 60} minutes due to blocks.")

                config['last_run_status'] = f"Backing off ({delay // 60}m due to blocks)"
                save_config(config)

                time.sleep(delay)

                # Decay block count after successful wait
                config = load_config()
                config['blocked_count'] = max(0, config['blocked_count'] - 1)
                save_config(config)

            # 2. Initialize Bot if needed
            if bot_manager is None:
                logger.info("Initializing BotManager...")
                bot_manager = BotManager(config.get('proxy'))

            # 3. Run Check Cycle
            config['last_run_status'] = "Checking stock..."
            save_config(config)

            found_items, was_blocked = bot_manager.run_check(config.get('bags', {}))

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            config = load_config() # Reload to reduce race conditions

            if was_blocked:
                config['blocked_count'] = config.get('blocked_count', 0) + 1
                config['last_blocked_time'] = timestamp
                config['last_run_status'] = f"⚠️ BLOCKED (Count: {config['blocked_count']})"
                logger.error(f"Bot blocked. Total blocks: {config['blocked_count']}")

                # Force restart on block
                if bot_manager:
                    bot_manager.cleanup()
                    bot_manager = None

            else:
                # Success
                config['success_count'] = config.get('success_count', 0) + 1
                config['blocked_count'] = max(0, config.get('blocked_count', 0) - 1) # Decay
                config['last_run_time'] = timestamp
                config['last_run_status'] = f"✓ Healthy (Found: {len(found_items)})"

                if found_items:
                    logger.info(f"🎉 Found {len(found_items)} items! Sending email.")
                    send_html_email(found_items, config.get('emails', []))

                consecutive_errors = 0

            save_config(config)

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Worker Exception: {e}", exc_info=True)

            config = load_config()
            config['last_run_status'] = f"Error: {str(e)[:50]}"
            save_config(config)

            if consecutive_errors >= 3:
                logger.critical("Too many errors. Restarting BotManager.")
                if bot_manager:
                    bot_manager.cleanup()
                    bot_manager = None
                consecutive_errors = 0

        # 4. Wait for next cycle
        config = load_config()
        min_m = config.get('min_interval_minutes', 20)
        max_m = config.get('max_interval_minutes', 40)

        wait_sec = random.randint(min_m * 60, max_m * 60)
        logger.info(f"Sleeping for {wait_sec // 60}m {wait_sec % 60}s...")
        time.sleep(wait_sec)


# -------------------------------------------------------------------------
# Flask Routes
# -------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html', config=load_config())

@app.route('/update_settings', methods=['POST'])
def update_settings():
    config = load_config()
    try:
        config['min_interval_minutes'] = int(request.form.get('min_time', 20))
        config['max_interval_minutes'] = int(request.form.get('max_time', 40))

        emails_str = request.form.get('emails', '')
        config['emails'] = [e.strip() for e in emails_str.split(',') if e.strip()]

        new_proxy = request.form.get('proxy', '').strip()
        if new_proxy != config.get('proxy', ''):
            logger.info("Proxy updated. Triggering browser restart.")
            global bot_manager
            if bot_manager:
                bot_manager.cleanup()
                bot_manager = None

        config['proxy'] = new_proxy
        save_config(config)
    except ValueError:
        logger.warning("Invalid input in settings update")

    return redirect(url_for('index'))

@app.route('/add_bag_group', methods=['POST'])
def add_bag_group():
    config = load_config()
    name = request.form.get('bag_name', '').strip()
    if name and name not in config['bags']:
        config['bags'][name] = {"active": True, "urls": []}
        save_config(config)
    return redirect(url_for('index'))

@app.route('/delete_bag_group/<name>')
def delete_bag_group(name):
    config = load_config()
    if name in config['bags']:
        del config['bags'][name]
        save_config(config)
    return redirect(url_for('index'))

@app.route('/toggle_bag_group/<name>')
def toggle_bag_group(name):
    config = load_config()
    if name in config['bags']:
        config['bags'][name]['active'] = not config['bags'][name].get('active', True)
        save_config(config)
    return redirect(url_for('index'))

@app.route('/add_url_to_group', methods=['POST'])
def add_url_to_group():
    config = load_config()
    group = request.form.get('group_name')
    url = request.form.get('url', '').strip().rstrip('/')

    if group in config['bags'] and url:
        urls = config['bags'][group]['urls']
        if url not in [u.rstrip('/') for u in urls]:
            config['bags'][group]['urls'].append(url)
            save_config(config)

    return redirect(url_for('index'))

@app.route('/remove_url', methods=['POST'])
def remove_url():
    config = load_config()
    group = request.form.get('group_name')
    url = request.form.get('url')

    if group in config['bags'] and url in config['bags'][group]['urls']:
        config['bags'][group]['urls'].remove(url)
        save_config(config)

    return redirect(url_for('index'))

@app.route('/test_email')
def test_email():
    config = load_config()
    recipients = config.get('emails', [])

    if not recipients:
        return redirect(url_for('index'))

    dummy_item = {
        "name": "TEST BAG (Picotin Lock 18)",
        "color": "Prunoir",
        "group": "Test Group",
        "link": "https://www.hermes.com/uk/en/",
        "image": "https://assets.hermes.com/is/image/hermesproduct/picotin-lock-18-bag--056289CK3W-front-1-300-0-800-800_g.jpg"
    }

    logger.info(f"Sending test email to {recipients}")
    send_html_email([dummy_item], recipients)
    return redirect(url_for('index'))

@app.route('/reset_stats')
def reset_stats():
    config = load_config()
    config.update({
        'blocked_count': 0,
        'success_count': 0,
        'last_blocked_time': None
    })
    save_config(config)
    return redirect(url_for('index'))

@app.route('/restart_browser')
def restart_browser():
    global bot_manager
    if bot_manager:
        logger.info("Manual browser restart triggered.")
        bot_manager.cleanup()
        bot_manager = None
    return redirect(url_for('index'))


# -------------------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------------------
if __name__ == '__main__':
    # 1. Start Virtual Display (Crucial for Headless Chrome)
    start_display()

    # 2. Start Background Worker
    logger.info("Starting background worker thread...")
    thread = threading.Thread(target=background_worker, daemon=True)
    thread.start()

    # 3. Start Flask App
    # use_reloader=False is mandatory when using background threads
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
