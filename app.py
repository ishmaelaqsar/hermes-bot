import time
import random
import json
import threading
import datetime
from flask import Flask, render_template, request, redirect, url_for
from bot_logic import run_check, send_html_email


app = Flask(__name__)
CONFIG_FILE = 'config.json'


# --- Load/Save Config Helpers ---
def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)


# --- Background Worker ---
def background_worker():
    while True:
        config = load_config()

        # 1. Update status
        config['last_run_status'] = "Running..."
        save_config(config)

        # 2. Run the Scraper
        found = run_check(config['ignore_list'])

        # 3. Handle Results
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        config = load_config() # Reload in case user changed settings while running
        config['last_run_time'] = timestamp
        config['found_items'] = found
        config['last_run_status'] = f"Waiting (Last found: {len(found)})"
        save_config(config)

        # 4. Send Email if items found
        if found:
            send_html_email(found, config['emails'])

        # 5. Wait random time
        min_min = int(config.get('min_interval_minutes', 10))
        max_min = int(config.get('max_interval_minutes', 20))
        wait_seconds = random.randint(min_min * 60, max_min * 60)
        print(f"Waiting {wait_seconds}s until next run...")
        time.sleep(wait_seconds)


# Start background thread immediately
thread = threading.Thread(target=background_worker, daemon=True)
thread.start()


# --- Web Routes ---
@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', config=config)


@app.route('/update_settings', methods=['POST'])
def update_settings():
    config = load_config()

    # Update Timing
    config['min_interval_minutes'] = int(request.form.get('min_time'))
    config['max_interval_minutes'] = int(request.form.get('max_time'))

    # Update Emails (Comma separated)
    emails_raw = request.form.get('emails')
    config['emails'] = [e.strip() for e in emails_raw.split(',') if e.strip()]

    save_config(config)
    return redirect(url_for('index'))


@app.route('/add_ignore', methods=['POST'])
def add_ignore():
    config = load_config()
    word = request.form.get('ignore_word')
    if word and word not in config['ignore_list']:
        config['ignore_list'].append(word)
        save_config(config)
    return redirect(url_for('index'))


@app.route('/remove_ignore/<word>')
def remove_ignore(word):
    config = load_config()
    if word in config['ignore_list']:
        config['ignore_list'].remove(word)
        save_config(config)
    return redirect(url_for('index'))


if __name__ == '__main__':
    # Host 0.0.0.0 allows access from other computers on network
    app.run(host='0.0.0.0', port=5000, debug=False)
