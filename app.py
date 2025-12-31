import time
import random
import json
import threading
import datetime
from flask import Flask, render_template, request, redirect, url_for
from bot_logic import run_check, send_html_email


app = Flask(__name__)
CONFIG_FILE = 'config.json'


def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            # Ensure new structure exists if migrating from old config
            if "bags" not in data:
                data["bags"] = {}
            return data
    except FileNotFoundError:
        return {
            "bags": {},
            "emails": [],
            "min_interval_minutes": 10,
            "max_interval_minutes": 20,
            "proxy": ""
        }


def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def background_worker():
    while True:
        config = load_config()

        try:
            # 1. Update status
            config['last_run_status'] = "Running..."
            save_config(config)

            # 2. Run the Scraper
            # Pass the entire 'bags' dict logic
            found = run_check(config.get('bags', {}), config.get('proxy'))

            # 3. Handle Success
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            config = load_config()
            config['last_run_time'] = timestamp
            config['found_items'] = found
            config['last_run_status'] = f"Waiting (Last found: {len(found)})"
            save_config(config)

            if found:
                send_html_email(found, config['emails'])

        except Exception as e:
            print(f"Worker Error: {e}")
            config = load_config()
            config['last_run_status'] = f"Error: {str(e)[:50]}..."
            save_config(config)

        # 5. Wait
        min_min = int(config.get('min_interval_minutes', 10))
        max_min = int(config.get('max_interval_minutes', 20))
        wait_seconds = random.randint(min_min * 60, max_min * 60)
        time.sleep(wait_seconds)


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
    config['proxy'] = request.form.get('proxy', '').strip()
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
    new_url = request.form.get('url').strip()

    if group_name in config['bags'] and new_url:
        if new_url not in config['bags'][group_name]['urls']:
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
        print("No recipients configured.")
        return redirect(url_for('index'))

    # Create dummy data
    dummy_items = [{
        "name": "TEST BAG (Picotin 18)",
        "color": "Gold / Silver",
        "group": "Test Group",
        "link": "https://www.hermes.com/uk/en/",
        "image": "https://assets.hermes.com/is/image/hermesproduct/picotin-lock-18-bag--056289CK37-front-1-300-0-1600-1600-q99_b.jpg"
    }]

    print(f"Sending test email to {recipients}...")
    send_html_email(dummy_items, recipients)

    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
