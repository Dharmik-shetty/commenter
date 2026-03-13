"""
AI Comment Automation Bot — Flask Application
Main entry point with all routes and API endpoints.
"""

import os
import json
import logging
from datetime import datetime, date

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO

from config import Config
from models import db, Account, Subreddit, Keyword, CommentLog, BotSettings, BotSession
from core.gemini_ai import GeminiAI
from core.semantic_matcher import SemanticMatcher
from core.scheduler import CommentScheduler

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
os.makedirs('data', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('data/bot.log', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)
socketio = SocketIO(app, async_mode='threading')

# Ensure data directories exist
os.makedirs('data/screenshots', exist_ok=True)

db.init_app(app)
with app.app_context():
    db.create_all()

# ---------------------------------------------------------------------------
# Global instances
# ---------------------------------------------------------------------------
gemini_ai = GeminiAI(
    api_key=Config.GEMINI_API_KEY,
    model_name=Config.GEMINI_MODEL,
    temperature=Config.GEMINI_TEMPERATURE,
    max_tokens=Config.GEMINI_MAX_TOKENS,
    top_p=Config.GEMINI_TOP_P,
    top_k=Config.GEMINI_TOP_K,
)

semantic_matcher = SemanticMatcher(model_name=Config.SEMANTIC_MODEL)
scheduler = CommentScheduler()

# ---------------------------------------------------------------------------
# Helper: log a comment to DB and emit via WebSocket
# ---------------------------------------------------------------------------
def log_comment(platform, username, post_url, post_title, comment_text,
                status, error='', source='', match_score=None):
    with app.app_context():
        entry = CommentLog(
            platform=platform,
            account_username=username,
            post_url=post_url,
            post_title=post_title,
            comment_text=comment_text,
            status=status,
            error_message=error,
            subreddit=source if platform == 'reddit' else '',
            search_keyword=source if platform != 'reddit' else '',
            match_score=match_score,
        )
        db.session.add(entry)

        # Update account comment count
        acc = Account.query.filter_by(platform=platform, username=username).first()
        if acc:
            acc.reset_daily_count()
            if status == 'success':
                acc.comments_today += 1
                acc.last_comment_at = datetime.utcnow()
            db.session.commit()
        else:
            db.session.commit()

    # Real-time push to dashboard
    socketio.emit('new_log', entry.to_dict())


# ═══════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/reddit')
def reddit_page():
    return render_template('reddit.html')


@app.route('/instagram')
def instagram_page():
    return render_template('instagram.html')


@app.route('/youtube')
def youtube_page():
    return render_template('youtube.html')


@app.route('/accounts')
def accounts_page():
    return render_template('accounts.html')


@app.route('/ai-settings')
def ai_settings_page():
    return render_template('ai_settings.html')


@app.route('/logs')
def logs_page():
    return render_template('logs.html')


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD API
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/dashboard/stats')
def dashboard_stats():
    today = date.today()

    total_today = CommentLog.query.filter(
        db.func.date(CommentLog.created_at) == today
    ).count()

    success_today = CommentLog.query.filter(
        db.func.date(CommentLog.created_at) == today,
        CommentLog.status == 'success'
    ).count()

    failed_today = CommentLog.query.filter(
        db.func.date(CommentLog.created_at) == today,
        CommentLog.status == 'failed'
    ).count()

    active_accounts = Account.query.filter_by(is_active=True).count()
    running_bots = scheduler.active_count()

    rate = (success_today / total_today * 100) if total_today > 0 else 0

    # Per-platform breakdown
    platforms = {}
    for p in ['reddit', 'instagram', 'youtube']:
        p_total = CommentLog.query.filter(
            db.func.date(CommentLog.created_at) == today,
            CommentLog.platform == p
        ).count()
        p_success = CommentLog.query.filter(
            db.func.date(CommentLog.created_at) == today,
            CommentLog.platform == p,
            CommentLog.status == 'success'
        ).count()
        p_accounts = Account.query.filter_by(platform=p, is_active=True).count()
        p_running = sum(1 for tid, s in scheduler.get_all_statuses().items()
                        if s == 'running' and tid.startswith(p))

        platforms[p] = {
            'total': p_total,
            'success': p_success,
            'accounts': p_accounts,
            'running': p_running,
        }

    return jsonify({
        'total_today': total_today,
        'success_today': success_today,
        'failed_today': failed_today,
        'success_rate': round(rate, 1),
        'active_accounts': active_accounts,
        'running_bots': running_bots,
        'platforms': platforms,
    })


# ═══════════════════════════════════════════════════════════════════════════
# ACCOUNT CRUD API
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    platform = request.args.get('platform')
    q = Account.query
    if platform:
        q = q.filter_by(platform=platform)
    accounts = q.order_by(Account.created_at.desc()).all()
    return jsonify([a.to_dict() for a in accounts])


@app.route('/api/accounts', methods=['POST'])
def add_account():
    data = request.json
    acc = Account(
        platform=data['platform'],
        username=data['username'],
        password=data['password'],  # In production, encrypt this
        email=data.get('email', ''),
        proxy=data.get('proxy', ''),
        user_agent=data.get('user_agent', ''),
        daily_limit=int(data.get('daily_limit', 1000)),
    )
    db.session.add(acc)
    db.session.commit()
    logger.info(f"Account added: {acc.platform}/{acc.username}")
    return jsonify(acc.to_dict()), 201


@app.route('/api/accounts/<int:account_id>', methods=['PUT'])
def update_account(account_id):
    acc = Account.query.get_or_404(account_id)
    data = request.json
    for field in ['username', 'password', 'email', 'proxy', 'user_agent',
                  'is_active', 'daily_limit']:
        if field in data:
            setattr(acc, field, data[field])
    db.session.commit()
    return jsonify(acc.to_dict())


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    acc = Account.query.get_or_404(account_id)
    db.session.delete(acc)
    db.session.commit()
    logger.info(f"Account deleted: {acc.platform}/{acc.username}")
    return jsonify({'status': 'deleted'})


# ═══════════════════════════════════════════════════════════════════════════
# SUBREDDIT CRUD API
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/subreddits', methods=['GET'])
def get_subreddits():
    subs = Subreddit.query.order_by(Subreddit.name).all()
    return jsonify([s.to_dict() for s in subs])


@app.route('/api/subreddits', methods=['POST'])
def add_subreddit():
    data = request.json
    name = data['name'].strip().replace('r/', '').replace('/r/', '')
    existing = Subreddit.query.filter_by(name=name).first()
    if existing:
        return jsonify({'error': f'r/{name} already exists'}), 409
    sub = Subreddit(
        name=name,
        sort_method=data.get('sort_method', 'hot'),
        posts_per_visit=int(data.get('posts_per_visit', 20)),
    )
    db.session.add(sub)
    db.session.commit()
    return jsonify(sub.to_dict()), 201


@app.route('/api/subreddits/<int:sub_id>', methods=['PUT'])
def update_subreddit(sub_id):
    sub = Subreddit.query.get_or_404(sub_id)
    data = request.json
    for field in ['sort_method', 'is_active', 'posts_per_visit']:
        if field in data:
            setattr(sub, field, data[field])
    db.session.commit()
    return jsonify(sub.to_dict())


@app.route('/api/subreddits/<int:sub_id>', methods=['DELETE'])
def delete_subreddit(sub_id):
    sub = Subreddit.query.get_or_404(sub_id)
    db.session.delete(sub)
    db.session.commit()
    return jsonify({'status': 'deleted'})


# ═══════════════════════════════════════════════════════════════════════════
# KEYWORD CRUD API
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/keywords', methods=['GET'])
def get_keywords():
    platform = request.args.get('platform')
    q = Keyword.query
    if platform:
        q = q.filter_by(platform=platform)
    keywords = q.order_by(Keyword.created_at.desc()).all()
    return jsonify([k.to_dict() for k in keywords])


@app.route('/api/keywords', methods=['POST'])
def add_keyword():
    data = request.json
    kw = Keyword(
        platform=data['platform'],
        keyword=data['keyword'].strip(),
    )
    db.session.add(kw)
    db.session.commit()
    return jsonify(kw.to_dict()), 201


@app.route('/api/keywords/<int:kw_id>', methods=['DELETE'])
def delete_keyword(kw_id):
    kw = Keyword.query.get_or_404(kw_id)
    db.session.delete(kw)
    db.session.commit()
    return jsonify({'status': 'deleted'})


# ═══════════════════════════════════════════════════════════════════════════
# SETTINGS API
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/settings', methods=['GET'])
def get_settings():
    defaults = {
        'gemini_api_key': Config.GEMINI_API_KEY,
        'gemini_model': Config.GEMINI_MODEL,
        'gemini_temperature': str(Config.GEMINI_TEMPERATURE),
        'gemini_max_tokens': str(Config.GEMINI_MAX_TOKENS),
        'gemini_top_p': str(Config.GEMINI_TOP_P),
        'gemini_top_k': str(Config.GEMINI_TOP_K),
        'reddit_preprompt': Config.DEFAULT_PREPROMPT,
        'instagram_preprompt': Config.INSTAGRAM_PREPROMPT,
        'youtube_preprompt': Config.YOUTUBE_PREPROMPT,
        'reddit_min_delay': str(Config.DEFAULT_MIN_DELAY),
        'reddit_max_delay': str(Config.DEFAULT_MAX_DELAY),
        'reddit_daily_limit': str(Config.DEFAULT_DAILY_LIMIT),
        'reddit_start_hour': str(Config.DEFAULT_START_HOUR),
        'reddit_end_hour': str(Config.DEFAULT_END_HOUR),
        'reddit_sort_method': Config.DEFAULT_SORT_METHOD,
        'reddit_posts_per_visit': str(Config.DEFAULT_POSTS_PER_VISIT),
        'reddit_match_threshold': str(Config.DEFAULT_MATCH_THRESHOLD),
        'instagram_min_delay': str(Config.DEFAULT_MIN_DELAY),
        'instagram_max_delay': str(Config.DEFAULT_MAX_DELAY),
        'instagram_daily_limit': str(Config.DEFAULT_DAILY_LIMIT),
        'instagram_start_hour': str(Config.DEFAULT_START_HOUR),
        'instagram_end_hour': str(Config.DEFAULT_END_HOUR),
        'youtube_min_delay': str(Config.DEFAULT_MIN_DELAY),
        'youtube_max_delay': str(Config.DEFAULT_MAX_DELAY),
        'youtube_daily_limit': str(Config.DEFAULT_DAILY_LIMIT),
        'youtube_start_hour': str(Config.DEFAULT_START_HOUR),
        'youtube_end_hour': str(Config.DEFAULT_END_HOUR),
        'headless_mode': 'true',
        'max_concurrent': str(Config.DEFAULT_MAX_CONCURRENT),
        'concurrent_reddit': str(Config.DEFAULT_CONCURRENT_REDDIT),
        'concurrent_instagram': str(Config.DEFAULT_CONCURRENT_INSTAGRAM),
        'concurrent_youtube': str(Config.DEFAULT_CONCURRENT_YOUTUBE),
    }

    settings = {}
    for key, default in defaults.items():
        settings[key] = BotSettings.get(key, default)

    return jsonify(settings)


@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    for key, value in data.items():
        BotSettings.set(key, value)

    # Update Gemini AI if relevant keys changed
    if any(k.startswith('gemini_') for k in data):
        gemini_ai.update_config(
            api_key=BotSettings.get('gemini_api_key', Config.GEMINI_API_KEY),
            model_name=BotSettings.get('gemini_model', Config.GEMINI_MODEL),
            temperature=float(BotSettings.get('gemini_temperature', Config.GEMINI_TEMPERATURE)),
            max_tokens=int(BotSettings.get('gemini_max_tokens', Config.GEMINI_MAX_TOKENS)),
            top_p=float(BotSettings.get('gemini_top_p', Config.GEMINI_TOP_P)),
            top_k=int(BotSettings.get('gemini_top_k', Config.GEMINI_TOP_K)),
        )

    logger.info(f"Settings saved: {list(data.keys())}")
    return jsonify({'status': 'saved'})


@app.route('/api/settings/test-ai', methods=['POST'])
def test_ai():
    ok = gemini_ai.test_connection()
    return jsonify({'connected': ok})


# ═══════════════════════════════════════════════════════════════════════════
# LOGS API
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/logs', methods=['GET'])
def get_logs():
    platform = request.args.get('platform')
    status = request.args.get('status')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    q = CommentLog.query
    if platform:
        q = q.filter_by(platform=platform)
    if status:
        q = q.filter_by(status=status)

    total = q.count()
    logs = q.order_by(CommentLog.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify({'total': total, 'logs': [l.to_dict() for l in logs]})


@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    CommentLog.query.delete()
    db.session.commit()
    return jsonify({'status': 'cleared'})


# ═══════════════════════════════════════════════════════════════════════════
# BOT CONTROL API
# ═══════════════════════════════════════════════════════════════════════════

def _get_platform_settings(platform):
    """Load bot-specific settings from DB."""
    return {
        'min_delay': float(BotSettings.get(f'{platform}_min_delay', Config.DEFAULT_MIN_DELAY)),
        'max_delay': float(BotSettings.get(f'{platform}_max_delay', Config.DEFAULT_MAX_DELAY)),
        'daily_limit': int(BotSettings.get(f'{platform}_daily_limit', Config.DEFAULT_DAILY_LIMIT)),
        'start_hour': int(BotSettings.get(f'{platform}_start_hour', Config.DEFAULT_START_HOUR)),
        'end_hour': int(BotSettings.get(f'{platform}_end_hour', Config.DEFAULT_END_HOUR)),
        'headless': BotSettings.get('headless_mode', 'true') == 'true',
    }


def _apply_concurrency_settings():
    """Read concurrency settings from DB and apply to the scheduler."""
    max_concurrent = int(BotSettings.get('max_concurrent', Config.DEFAULT_MAX_CONCURRENT))
    scheduler.set_concurrency_limit(max_concurrent)
    return max_concurrent


def _get_platform_concurrency(platform):
    """Get the max concurrent accounts for a specific platform."""
    defaults = {
        'reddit': Config.DEFAULT_CONCURRENT_REDDIT,
        'instagram': Config.DEFAULT_CONCURRENT_INSTAGRAM,
        'youtube': Config.DEFAULT_CONCURRENT_YOUTUBE,
    }
    return int(BotSettings.get(f'concurrent_{platform}', defaults.get(platform, 2)))


def _validate_account_proxies(accounts):
    """
    Check that accounts have unique proxies and warn about missing ones.
    Returns (warnings, errors) lists.
    """
    warnings = []
    proxy_map = {}  # proxy -> [usernames]

    for acc in accounts:
        if not acc.proxy:
            warnings.append(
                f"{acc.platform}/{acc.username}: No proxy configured — "
                f"will use your real IP (high detection risk)"
            )
        else:
            proxy_map.setdefault(acc.proxy, []).append(f"{acc.platform}/{acc.username}")

    # Check for shared proxies
    for proxy, users in proxy_map.items():
        if len(users) > 1:
            warnings.append(
                f"Shared proxy detected: {', '.join(users)} all use the same proxy. "
                f"Use unique proxies per account to avoid detection."
            )

    for w in warnings:
        logger.warning(f"[Proxy] {w}")

    return warnings


@app.route('/api/bot/reddit/start', methods=['POST'])
def start_reddit_bot():
    from bots.reddit_bot import run_reddit_bot

    accounts = Account.query.filter_by(platform='reddit', is_active=True).all()
    if not accounts:
        return jsonify({'error': 'No active Reddit accounts'}), 400

    # Validate proxies — warn about missing/shared proxies
    proxy_warnings = _validate_account_proxies(accounts)

    # Apply concurrency settings
    _apply_concurrency_settings()
    platform_limit = _get_platform_concurrency('reddit')

    subreddits = Subreddit.query.filter_by(is_active=True).all()
    if not subreddits:
        return jsonify({'error': 'No active subreddits configured'}), 400

    keywords_db = Keyword.query.filter_by(platform='reddit', is_active=True).all()
    keyword_list = [k.keyword for k in keywords_db]

    if keyword_list:
        semantic_matcher.set_keywords(keyword_list)

    settings = _get_platform_settings('reddit')
    preprompt = BotSettings.get('reddit_preprompt', Config.DEFAULT_PREPROMPT)
    sort_method = BotSettings.get('reddit_sort_method', Config.DEFAULT_SORT_METHOD)
    match_threshold = float(BotSettings.get('reddit_match_threshold', Config.DEFAULT_MATCH_THRESHOLD))
    posts_per_visit = int(BotSettings.get('reddit_posts_per_visit', Config.DEFAULT_POSTS_PER_VISIT))

    sub_configs = [s.to_dict() for s in subreddits]

    # Only start up to platform_limit accounts; rest will be queued
    started = []
    queued = []
    for acc in accounts:
        task_id = f"reddit_{acc.username}"
        if scheduler.is_running(task_id):
            continue

        acc.status = 'running'
        db.session.commit()

        acc_dict = {
            'username': acc.username,
            'password': acc.password,
            'proxy': acc.proxy,
            'user_agent': acc.user_agent,
            'comments_today': acc.comments_today,
        }

        scheduler.start_task(
            task_id,
            run_reddit_bot,
            account=acc_dict,
            subreddits=sub_configs,
            keywords=keyword_list,
            ai_generator=gemini_ai,
            semantic_matcher=semantic_matcher if keyword_list else None,
            daily_limit=settings['daily_limit'],
            min_delay=settings['min_delay'],
            max_delay=settings['max_delay'],
            sort_method=sort_method,
            posts_per_visit=posts_per_visit,
            match_threshold=match_threshold,
            start_hour=settings['start_hour'],
            end_hour=settings['end_hour'],
            headless=settings['headless'],
            log_callback=log_comment,
        )

        if len(started) < platform_limit:
            started.append(acc.username)
        else:
            queued.append(acc.username)

    result = {
        'started': started, 'queued': queued,
        'count': len(started), 'queued_count': len(queued),
        'platform_limit': platform_limit,
    }
    if proxy_warnings:
        result['proxy_warnings'] = proxy_warnings
    return jsonify(result)


@app.route('/api/bot/reddit/stop', methods=['POST'])
def stop_reddit_bot():
    accounts = Account.query.filter_by(platform='reddit').all()
    stopped = []
    for acc in accounts:
        task_id = f"reddit_{acc.username}"
        if scheduler.is_running(task_id):
            scheduler.stop_task(task_id)
            acc.status = 'idle'
            stopped.append(acc.username)
    db.session.commit()
    return jsonify({'stopped': stopped})


@app.route('/api/bot/instagram/start', methods=['POST'])
def start_instagram_bot():
    from bots.instagram_bot import run_instagram_bot

    accounts = Account.query.filter_by(platform='instagram', is_active=True).all()
    if not accounts:
        return jsonify({'error': 'No active Instagram accounts'}), 400

    # Validate proxies
    proxy_warnings = _validate_account_proxies(accounts)

    # Apply concurrency settings
    _apply_concurrency_settings()
    platform_limit = _get_platform_concurrency('instagram')

    keywords_db = Keyword.query.filter_by(platform='instagram', is_active=True).all()
    keyword_list = [k.keyword for k in keywords_db]
    if not keyword_list:
        return jsonify({'error': 'No search keywords configured'}), 400

    settings = _get_platform_settings('instagram')
    preprompt = BotSettings.get('instagram_preprompt', Config.INSTAGRAM_PREPROMPT)

    started = []
    queued = []
    for acc in accounts:
        task_id = f"instagram_{acc.username}"
        if scheduler.is_running(task_id):
            continue

        acc.status = 'running'
        db.session.commit()

        acc_dict = {
            'username': acc.username,
            'password': acc.password,
            'proxy': acc.proxy,
            'user_agent': acc.user_agent,
            'comments_today': acc.comments_today,
        }

        scheduler.start_task(
            task_id,
            run_instagram_bot,
            account=acc_dict,
            search_keywords=keyword_list,
            ai_generator=gemini_ai,
            daily_limit=settings['daily_limit'],
            min_delay=settings['min_delay'],
            max_delay=settings['max_delay'],
            preprompt=preprompt,
            start_hour=settings['start_hour'],
            end_hour=settings['end_hour'],
            headless=settings['headless'],
            log_callback=log_comment,
        )

        if len(started) < platform_limit:
            started.append(acc.username)
        else:
            queued.append(acc.username)

    result = {
        'started': started, 'queued': queued,
        'count': len(started), 'queued_count': len(queued),
        'platform_limit': platform_limit,
    }
    if proxy_warnings:
        result['proxy_warnings'] = proxy_warnings
    return jsonify(result)


@app.route('/api/bot/instagram/stop', methods=['POST'])
def stop_instagram_bot():
    accounts = Account.query.filter_by(platform='instagram').all()
    stopped = []
    for acc in accounts:
        task_id = f"instagram_{acc.username}"
        if scheduler.is_running(task_id):
            scheduler.stop_task(task_id)
            acc.status = 'idle'
            stopped.append(acc.username)
    db.session.commit()
    return jsonify({'stopped': stopped})


@app.route('/api/bot/youtube/start', methods=['POST'])
def start_youtube_bot():
    from bots.youtube_bot import run_youtube_bot

    accounts = Account.query.filter_by(platform='youtube', is_active=True).all()
    if not accounts:
        return jsonify({'error': 'No active YouTube accounts'}), 400

    # Validate proxies
    proxy_warnings = _validate_account_proxies(accounts)

    # Apply concurrency settings
    _apply_concurrency_settings()
    platform_limit = _get_platform_concurrency('youtube')

    keywords_db = Keyword.query.filter_by(platform='youtube', is_active=True).all()
    keyword_list = [k.keyword for k in keywords_db]
    if not keyword_list:
        return jsonify({'error': 'No search keywords configured'}), 400

    settings = _get_platform_settings('youtube')
    preprompt = BotSettings.get('youtube_preprompt', Config.YOUTUBE_PREPROMPT)

    started = []
    queued = []
    for acc in accounts:
        task_id = f"youtube_{acc.username}"
        if scheduler.is_running(task_id):
            continue

        acc.status = 'running'
        db.session.commit()

        acc_dict = {
            'username': acc.username,
            'password': acc.password,
            'email': acc.email,
            'proxy': acc.proxy,
            'user_agent': acc.user_agent,
            'comments_today': acc.comments_today,
        }

        scheduler.start_task(
            task_id,
            run_youtube_bot,
            account=acc_dict,
            search_keywords=keyword_list,
            ai_generator=gemini_ai,
            daily_limit=settings['daily_limit'],
            min_delay=settings['min_delay'],
            max_delay=settings['max_delay'],
            preprompt=preprompt,
            start_hour=settings['start_hour'],
            end_hour=settings['end_hour'],
            headless=settings['headless'],
            log_callback=log_comment,
        )

        if len(started) < platform_limit:
            started.append(acc.username)
        else:
            queued.append(acc.username)

    result = {
        'started': started, 'queued': queued,
        'count': len(started), 'queued_count': len(queued),
        'platform_limit': platform_limit,
    }
    if proxy_warnings:
        result['proxy_warnings'] = proxy_warnings
    return jsonify(result)


@app.route('/api/bot/youtube/stop', methods=['POST'])
def stop_youtube_bot():
    accounts = Account.query.filter_by(platform='youtube').all()
    stopped = []
    for acc in accounts:
        task_id = f"youtube_{acc.username}"
        if scheduler.is_running(task_id):
            scheduler.stop_task(task_id)
            acc.status = 'idle'
            stopped.append(acc.username)
    db.session.commit()
    return jsonify({'stopped': stopped})


@app.route('/api/bot/start-all', methods=['POST'])
def start_all_bots():
    """Start all platforms respecting per-platform concurrency slots."""
    results = {}
    errors = []

    for platform in ['reddit', 'instagram', 'youtube']:
        try:
            with app.test_request_context():
                if platform == 'reddit':
                    resp = start_reddit_bot()
                elif platform == 'instagram':
                    resp = start_instagram_bot()
                else:
                    resp = start_youtube_bot()

                if isinstance(resp, tuple):
                    # Error response (jsonify, status_code)
                    errors.append({'platform': platform, 'error': resp[0].get_json().get('error', 'Unknown error')})
                else:
                    results[platform] = resp.get_json()
        except Exception as e:
            errors.append({'platform': platform, 'error': str(e)})

    return jsonify({'results': results, 'errors': errors})


@app.route('/api/bot/stop-all', methods=['POST'])
def stop_all_bots():
    scheduler.stop_all()
    Account.query.update({'status': 'idle'})
    db.session.commit()
    return jsonify({'status': 'all stopped'})


@app.route('/api/bot/status')
def bot_status():
    return jsonify(scheduler.get_all_statuses())


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════════════════════

@socketio.on('connect')
def on_connect():
    logger.debug('WebSocket client connected')


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
