from flask import Flask, render_template, request, jsonify
import json
import os
import threading
import time
import datetime
from reddit_scraper import login_and_scrape_reddit, set_print_function, post_comment

from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# Global state for background task
scraper_status = "Not running"
scraper_logs = []
scraper_results = []
drivers_instances = {}
stop_requested = False
total_comments_posted = 0  # To track comments posted across runs
daily_limits = {} # Global state for daily limits
session_state = {} # Global state for session resumption

# To ensure thread safety when modifying shared lists
log_lock = threading.Lock()
result_lock = threading.Lock()
state_lock = threading.Lock() # Lock for state file operations

def load_state():
    global daily_limits, session_state
    if os.path.exists("state.json"):
        try:
            with open("state.json", "r") as f:
                data = json.load(f)
                daily_limits = data.get("daily_limits", {})
                session_state = data.get("session_state", {})
        except Exception as e:
            print(f"Error loading state: {e}")

def save_state():
    global daily_limits, session_state
    try:
        with state_lock:
            with open("state.json", "w") as f:
                json.dump({
                    "daily_limits": daily_limits,
                    "session_state": session_state
                }, f, indent=4)
    except Exception as e:
        print(f"Error saving state: {e}")

def load_settings():
    if os.path.exists("settings.json"):
        with open("settings.json", "r") as f:
            data = json.load(f)
            # Migration step: if old format, convert to accounts format
            if 'username' in data and 'accounts' not in data:
                data['accounts'] = [{
                    "username": data.pop("username", ""),
                    "password": data.pop("password", ""),
                    "proxy": "",
                    "enabled": True
                }]
                data['concurrent_accounts'] = 1
                save_settings_file(data)
            
            # Ensure advanced settings structure
            if 'advanced_settings' not in data:
                data['advanced_settings'] = {}
                
            return data
    return {"accounts": [], "concurrent_accounts": 1, "advanced_settings": {}}

def save_settings_file(settings):
    with open("settings.json", "w") as f:
        json.dump(settings, f, indent=4)

def custom_print(message):
    with log_lock:
        global scraper_logs
        scraper_logs.append({"time": time.strftime("%H:%M:%S"), "message": message})
        with open('log.txt', 'a', encoding='utf-8') as log_file:
            log_file.write(message + '\n')
        if len(scraper_logs) > 1000:
            scraper_logs = scraper_logs[-1000:]

def parse_proxy(proxy_str):
    if not proxy_str:
        return {"enabled": False}
    # Expected format: host:port:username:password or host:port
    parts = proxy_str.split(':')
    proxy = {
        "enabled": True,
        "type": "http", # default
        "host": parts[0] if len(parts) > 0 else '',
        "port": parts[1] if len(parts) > 1 else '80'
    }
    if len(parts) >= 4:
        proxy["username"] = parts[2]
        proxy["password"] = parts[3]
    return proxy

def is_within_time_window(start_str, end_str):
    if not start_str or not end_str:
        return True
    try:
        now = datetime.datetime.now().time()
        start = datetime.datetime.strptime(start_str, "%H:%M").time()
        end = datetime.datetime.strptime(end_str, "%H:%M").time()
        if start <= end:
            return start <= now <= end
        else: # passes midnight
            return now >= start or now <= end
    except ValueError:
        return True

def run_single_account(account, params, daily_limits):
    global stop_requested
    if stop_requested: return
    
    username = account.get('username')
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Use max_comments as per-run limit, and max_comments_per_day as overarching limit
    max_comments_per_day = params.get('advanced_settings', {}).get('max_comments_per_day', 50)
    
    with log_lock:
        if today_str not in daily_limits:
            daily_limits[today_str] = {}
        if username not in daily_limits[today_str]:
            daily_limits[today_str][username] = 0
        
    already_posted_today = daily_limits[today_str][username]
    if already_posted_today >= max_comments_per_day:
        custom_print(f"[{username}] Reached daily max comments ({max_comments_per_day}). Skipping.")
        return

    # To avoid exceeding the daily limit during this run
    allowed_this_run = min(params.get('max_comments', 100), max_comments_per_day - already_posted_today)
    
    def scoped_print(msg):
        custom_print(f"[{username}] {msg}")
        
    try:
        set_print_function(custom_print)
        scoped_print(f"Starting the scraping process... {allowed_this_run} comments allowed this run.")
        
        # Load session state for this user
        user_resume_state = {}
        with state_lock:
             if username in session_state:
                  user_resume_state = session_state[username]
                  scoped_print("Resuming from saved state.")

        def update_state_callback(new_data):
             with state_lock:
                  if username not in session_state:
                       session_state[username] = {}
                  session_state[username].update(new_data)
                  # Save state to disk periodically could be done here, but maybe too frequent?
                  # For crash safety, saving on every update is safer.
                  with open("state.json", "w") as f:
                        json.dump({
                            "daily_limits": daily_limits,
                            "session_state": session_state
                        }, f, indent=4)

        proxy_settings = parse_proxy(account.get('proxy', ''))
        
        all_results, driver = login_and_scrape_reddit(
            username=username,
            password=account.get('password'),
            subreddits=params.get('subreddits', []),
            sort_type=params.get('sort_type', 'new'),
            max_articles=params.get('max_articles', 100),
            max_comments=allowed_this_run,
            min_wait_time=params.get('min_wait_time', 50),
            max_wait_time=params.get('max_wait_time', 150),
            custom_headers=params.get('custom_headers'),
            ai_response_length=params.get('ai_response_length', 30),
            proxy_settings=proxy_settings,
            fingerprint_settings=params.get('fingerprint_settings', {}),
            do_not_post=params.get('do_not_post', False),
            gemini_api_key=params.get('advanced_settings', {}).get('gemini_api_key', ''),
            scroll_retries=params.get('advanced_settings', {}).get('scroll_retries', 3),
            button_retries=params.get('advanced_settings', {}).get('button_retries', 1),
            persona=params.get('advanced_settings', {}).get('persona', 'normal'),
            custom_model=params.get('advanced_settings', {}).get('custom_model', 'openai/o3-mini-high'),
            ai_batch_size=int(params.get('advanced_settings', {}).get('ai_batch_size', 1) or 1),
            ai_wait_time=int(params.get('advanced_settings', {}).get('ai_wait_time', 0) or 0),
            custom_prompt=params.get('advanced_settings', {}).get('custom_prompt', ''),
            product_keywords=params.get('advanced_settings', {}).get('product_keywords', ''),
            similarity_threshold=params.get('advanced_settings', {}).get('similarity_threshold', 0.18),
            similarity_method=params.get('advanced_settings', {}).get('similarity_method', 'Simple (keyword matching only)'),
            tensorflow_sleep_time=params.get('advanced_settings', {}).get('tensorflow_sleep_time', 1.0),
            per_subreddit_max_posts_to_check=params.get('advanced_settings', {}).get('per_subreddit_max_posts_to_check', params.get('max_articles', 100)),
            existing_driver=None, # Always spawn new driver for parallel accounts
            resume_state=user_resume_state,
            update_state_callback=update_state_callback
        )
        
        scoped_print("Scraping completed.")
        
        # Clear session state for this user ONLY IF successfully completed FULL run
        # If we reached daily limit or finished subreddits, we reset the session state for next day
        # But if we stopped early, we keep it. The outer loop logic determines completion.
        # Actually, if we finished 'login_and_scrape_reddit' without exception, it means we finished the pass.
        # So we should reset the index and seen_urls for the NEXT run?
        # NO, 'seen_urls' should persist for the day or longer. The 'index' should reset if we want to loop.
        # However, the user asked for indefinite running. 
        # If we finish the list of subreddits, we typically want to start over from the first one on the next pass.
        # So, we reset 'current_subreddit_index' to 0 here.
        with state_lock:
             if username in session_state:
                  session_state[username]['current_subreddit_index'] = 0
                  # We KEEP seen_urls to avoid re-commenting on same posts in the next loop.
             save_state()
        
        # Determine actual comments posted/generated to add to daily limit
        with log_lock:
            global total_comments_posted
            if today_str not in daily_limits:
                daily_limits[today_str] = {}
            if username not in daily_limits[today_str]:
                daily_limits[today_str][username] = 0
            daily_limits[today_str][username] += len(all_results)
            save_state() # Save state after updating limits

        # Tag results with account username to review/post later with correct driver
        for r in all_results:
            r['account'] = username
            if r.get('post_successful'):
                with log_lock:
                    total_comments_posted += 1

        with result_lock:
            scraper_results.extend(all_results)
            # Auto-close driver as we are running in automated server mode
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                
    except Exception as e:
        scoped_print(f"Error: {str(e)}")

def run_scraper_manager(params):
    global scraper_status, scraper_results, drivers_instances, stop_requested, daily_limits
    scraper_status = "Running"
    scraper_results = []
    drivers_instances = {}
    stop_requested = False
    
    time_start = params.get('advanced_settings', {}).get('time_start', "")
    time_end = params.get('advanced_settings', {}).get('time_end', "")
    
    accounts = [acc for acc in params.get('accounts', []) if acc.get('enabled', True)]
    concurrent_limit = int(params.get('concurrent_accounts', 1))
    
    if not accounts:
        custom_print("No enabled accounts found to run.")
        scraper_status = "Completed"
        return

    # Load persistent state
    load_state()

    while not stop_requested:
        while not stop_requested and not is_within_time_window(time_start, time_end):
            custom_print(f"Outside of active time window ({time_start} - {time_end}). Sleeping for 60s...")
            for _ in range(60):
                if stop_requested: break
                time.sleep(1)

        if stop_requested:
            break

        # Clean up history for older days to prevent memory leak
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        daily_limits = {k: v for k, v in daily_limits.items() if k == today_str}

        with ThreadPoolExecutor(max_workers=max(1, concurrent_limit)) as executor:
            futures = {executor.submit(run_single_account, acc, params, daily_limits): acc for acc in accounts}
            for future in as_completed(futures):
                future.result()

        if not stop_requested:
            # Check if all accounts have reached their daily limit
            all_done = True
            for acc in accounts:
                username = acc.get('username')
                if username and daily_limits.get(today_str, {}).get(username, 0) < params.get('advanced_settings', {}).get('max_comments_per_day', 50):
                    all_done = False
                    break
            
            if all_done:
                custom_print(f"All accounts reached their daily max comments. Waiting for tomorrow...")
                for _ in range(3600): # Sleep 1 hour before checking again
                    if stop_requested: break
                    time.sleep(1)
            else:
                custom_print("Round completed. Waiting 60 seconds before next pass...")
                for _ in range(60):
                    if stop_requested: break
                    time.sleep(1)

    if stop_requested:
        custom_print("Scraping manually stopped.")
    else:
        custom_print("All accounts completed their tasks.")
        
    scraper_status = "Completed"
    stop_requested = False

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        new_settings = request.json
        save_settings_file(new_settings)
        return jsonify({"status": "success"})
    return jsonify(load_settings())

@app.route("/api/start", methods=["POST"])
def start_scraping():
    global scraper_thread, scraper_status, scraper_logs
    if scraper_status == "Running":
        return jsonify({"error": "Already running"}), 400
    
    settings_data = load_settings()
    # Default to False (auto-post) for server automation
    settings_data['do_not_post'] = request.json.get('do_not_post', False)
    scraper_logs = []
    
    scraper_thread = threading.Thread(target=run_scraper_manager, args=(settings_data,))
    scraper_thread.start()
    return jsonify({"status": "started"})

@app.route("/api/stop", methods=["POST"])
def stop_scraping():
    global stop_requested, scraper_status
    if scraper_status == "Running":
        stop_requested = True
        return jsonify({"status": "stopping"})
    return jsonify({"status": "not running"}), 400

@app.route("/api/reset_state", methods=["POST"])
def reset_state():
    global daily_limits
    try:
        with log_lock:
            daily_limits.clear()
        
        with state_lock:
            if os.path.exists("state.json"):
                os.remove("state.json")
        
        custom_print("State has been reset. Daily limits cleared.")
        return jsonify({"status": "reset"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/status", methods=["GET"])
def get_status():
    global scraper_status, scraper_logs, total_comments_posted
    return jsonify({
        "status": scraper_status,
        "logs": scraper_logs,
        "total_comments_posted": total_comments_posted
    })

@app.route("/api/results", methods=["GET"])
def get_results():
    global scraper_results
    return jsonify({"results": scraper_results})

@app.route("/api/post_comments", methods=["POST"])
def post_comments():
    global drivers_instances, total_comments_posted
    comments_to_post = request.json.get("comments", [])

    for comment in comments_to_post:
        username = comment.get('account')
        driver_instance = drivers_instances.get(username)

        if not driver_instance:
            custom_print(f"[{username}] Error: Driver not available for posting. Make sure the bot ran and left a driver open.")
            continue

        try:
            custom_print(f"[{username}] Posting comment for URL: {comment['url']}")
            success = post_comment(driver_instance, comment['ai_comment'], comment['url'])
            if success:
                with log_lock:
                    total_comments_posted += 1
            else:
                custom_print(f"[{username}] Failed to post comment on {comment['url']}")
        except Exception as e:
            custom_print(f"[{username}] Error posting comment on {comment['url']}: {e}")
            
    return jsonify({"status": "completed"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
