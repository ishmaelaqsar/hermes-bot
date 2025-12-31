import time
import random
import json
import threading
import datetime
import logging
import os
from flask import Flask, render_template, request, redirect, url_for
from bot_logic import BotManager, send_html_email


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CONFIG_FILE = 'config.json'


def kill_zombie_chrome():
    """Kills any lingering Chrome processes and unlocks the profile folder."""
    logger.info("Cleaning up zombie Chrome processes...")
    try:
        # 1. Kill the processes
        os.system("pkill -f chrome")
        os.system("pkill -f undetected_chromedriver")
        time.sleep(2)

        # 2. Force delete the Lock file
        cache_path = os.path.join(os.getcwd(), "chrome_cache")
        lock_file = os.path.join(cache_path, "SingletonLock")

        if os.path.exists(lock_file):
            logger.info(f"Removing stuck lock file: {lock_file}")
            os.remove(lock_file)

    except Exception as e:
        logger.warning(f"Cleanup warning: {e}")


# Run cleanup immediately on start
kill_zombie_chrome()

# Global bot manager instance
bot_manager = None


def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            if "bags" not in data:
                data["bags"] = {}
            if "blocked_count" not in data:
                data["blocked_count"] = 0
            if "success_count" not in data:
                data["success_count"] = 0
            if "last_blocked_time" not in data:
                data["last_blocked_time"] = None
            return data
    except FileNotFoundError:
        return {
            "bags": {},
            "emails": [],
            "min_interval_minutes": 10,
            "max_interval_minutes": 20,
            "proxy": "",
            "blocked_count": 0,
            "success_count": 0,
            "last_blocked_time": None
        }


def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def calculate_backoff_delay(blocked_count):
    """Calculate exponential backoff delay when blocked"""
    if blocked_count == 0:
        return 0

    # Exponential backoff: 5min, 15min, 30min, 1hr, 2hr (max)
    base_minutes = 5
    backoff_minutes = min(base_minutes * (2 ** (blocked_count - 1)), 120)

    # Add some randomization
    jitter = random.uniform(0.8, 1.2)
    return int(backoff_minutes * 60 * jitter)


def background_worker():
    global bot_manager

    logger.info("Background worker started")
    consecutive_errors = 0

    while True:
        config = load_config()

        try:
            # Check if we need to back off due to being blocked
            if config.get('blocked_count', 0) > 0:
                backoff_delay = calculate_backoff_delay(config['blocked_count'])
                logger.warning(f"Bot was blocked. Backing off for {backoff_delay // 60} minutes")

                config['last_run_status'] = f"Backing off ({backoff_delay // 60} min due to detection)"
                save_config(config)

                time.sleep(backoff_delay)

                # Reset blocked count after backoff
                config = load_config()
                config['blocked_count'] = max(0, config['blocked_count'] - 1)
                save_config(config)

            # Update status
            config['last_run_status'] = "Running..."
            save_config(config)

            # Initialize bot manager if needed
            if bot_manager is None:
                logger.info("Initializing bot manager")
                bot_manager = BotManager(config.get('proxy'))

            # Run the check
            logger.info("Starting check cycle")
            found, was_blocked = bot_manager.run_check(config.get('bags', {}))

            # Handle blocking
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            config = load_config()

            if was_blocked:
                config['blocked_count'] = config.get('blocked_count', 0) + 1
                config['last_blocked_time'] = timestamp
                config['last_run_status'] = f"⚠️ BLOCKED by anti-bot (Count: {config['blocked_count']})"
                logger.error(f"Bot was blocked! Total blocks: {config['blocked_count']}")

                # Restart browser after being blocked
                logger.info("Restarting browser after block")
                bot_manager.cleanup()
                bot_manager = None

            else:
                # Success
                config['success_count'] = config.get('success_count', 0) + 1
                config['blocked_count'] = max(0, config.get('blocked_count', 0) - 1)  # Decay block count
                config['last_run_time'] = timestamp
                config['found_items'] = found
                config['last_run_status'] = f"✓ Healthy (Found: {len(found)}, Success: {config['success_count']})"

                logger.info(f"Check completed successfully. Found {len(found)} items")

                # Send email if items found
                if found:
                    logger.info(f"Sending email notification for {len(found)} items")
                    send_html_email(found, config['emails'])

                consecutive_errors = 0  # Reset error counter

            save_config(config)

        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            consecutive_errors += 1

            config = load_config()
            config['last_run_status'] = f"Error: {str(e)[:50]}... (Count: {consecutive_errors})"
            save_config(config)

            # If too many consecutive errors, restart the browser
            if consecutive_errors >= 3:
                logger.warning("Too many consecutive errors. Restarting browser...")
                if bot_manager:
                    bot_manager.cleanup()
                    bot_manager = None
                consecutive_errors = 0

        # Calculate wait time
        config = load_config()
        min_min = int(config.get('min_interval_minutes', 10))
        max_min = int(config.get('max_interval_minutes', 20))

        # Add extra randomization to avoid patterns
        base_wait = random.randint(min_min * 60, max_min * 60)
        jitter = random.randint(-30, 30)  # +/- 30 seconds
        wait_seconds = max(60, base_wait + jitter)  # Minimum 1 minute

        logger.info(f"Waiting {wait_seconds // 60} minutes {wait_seconds % 60} seconds until next check")
        time.sleep(wait_seconds)


# Start background thread
thread = threading.Thread(target=background_worker, daemon=True)
thread.start()


@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', config=config)


@app.route('/update_settings', methods=['POST'])
def update_settings():
    config = load_config()
    config['min_interval_minutes'] = int(request.form.get('min_time'))
    config['max_interval_minutes'] = int(request.form.get('max_time'))
    emails_raw = request.form.get('emails')
    config['emails'] = [e.strip() for e in emails_raw.split(',') if e.strip()]

    new_proxy = request.form.get('proxy', '').strip()
    old_proxy = config.get('proxy', '')

    # If proxy changed, restart browser
    if new_proxy != old_proxy:
        global bot_manager
        if bot_manager:
            logger.info("Proxy changed, restarting browser")
            bot_manager.cleanup()
            bot_manager = None

    config['proxy'] = new_proxy
    save_config(config)
    return redirect(url_for('index'))


@app.route('/add_bag_group', methods=['POST'])
def add_bag_group():
    config = load_config()
    name = request.form.get('bag_name').strip()
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
        current_status = config['bags'][name].get('active', True)
        config['bags'][name]['active'] = not current_status
        save_config(config)
    return redirect(url_for('index'))


@app.route('/add_url_to_group', methods=['POST'])
def add_url_to_group():
    config = load_config()
    group_name = request.form.get('group_name')
    new_url = request.form.get('url', '').strip().rstrip('/')

    if group_name in config['bags'] and new_url:
        current_urls = config['bags'][group_name]['urls']

        is_duplicate = False
        for existing in current_urls:
            if existing.rstrip('/') == new_url:
                is_duplicate = True
                break

        if not is_duplicate:
            config['bags'][group_name]['urls'].append(new_url)
            save_config(config)

    return redirect(url_for('index'))


@app.route('/remove_url', methods=['POST'])
def remove_url():
    config = load_config()
    group_name = request.form.get('group_name')
    url_to_remove = request.form.get('url')

    if group_name in config['bags']:
        if url_to_remove in config['bags'][group_name]['urls']:
            config['bags'][group_name]['urls'].remove(url_to_remove)
            save_config(config)
    return redirect(url_for('index'))


@app.route('/test_email')
def test_email():
    config = load_config()
    recipients = config.get('emails', [])

    if not recipients:
        logger.warning("No recipients configured for test email")
        return redirect(url_for('index'))

    dummy_items = [{
        "name": "TEST BAG (Picotin Lock 18)",
        "color": "Prunoir",
        "group": "Test Group",
        "link": "https://www.hermes.com/uk/en/product/picotin-lock-18-bag-H056289CK3W/",
        "image": "https://assets.hermes.com/is/image/hermesproduct/picotin-lock-18-bag--056289CK3W-front-1-300-0-800-800_g.jpg"
    }]

    logger.info(f"Sending test email to {recipients}")
    send_html_email(dummy_items, recipients)

    return redirect(url_for('index'))


@app.route('/reset_stats')
def reset_stats():
    """Reset block counters"""
    config = load_config()
    config['blocked_count'] = 0
    config['success_count'] = 0
    config['last_blocked_time'] = None
    save_config(config)
    logger.info("Statistics reset")
    return redirect(url_for('index'))


@app.route('/restart_browser')
def restart_browser():
    """Manually restart the browser"""
    global bot_manager
    if bot_manager:
        logger.info("Manual browser restart requested")
        bot_manager.cleanup()
        bot_manager = None
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
