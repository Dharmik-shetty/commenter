from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Account(db.Model):
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(20), nullable=False)  # reddit, instagram, youtube
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(500), nullable=False)  # encrypted
    email = db.Column(db.String(200), nullable=True)
    proxy = db.Column(db.String(300), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    daily_limit = db.Column(db.Integer, default=1000)
    comments_today = db.Column(db.Integer, default=0)
    last_comment_at = db.Column(db.DateTime, nullable=True)
    last_reset_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='idle')  # idle, running, paused, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def reset_daily_count(self):
        today = datetime.utcnow().date()
        if self.last_reset_date != today:
            self.comments_today = 0
            self.last_reset_date = today

    def to_dict(self):
        return {
            'id': self.id,
            'platform': self.platform,
            'username': self.username,
            'email': self.email or '',
            'proxy': self.proxy or '',
            'user_agent': self.user_agent or '',
            'is_active': self.is_active,
            'daily_limit': self.daily_limit,
            'comments_today': self.comments_today,
            'last_comment_at': self.last_comment_at.isoformat() if self.last_comment_at else None,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
        }


class Subreddit(db.Model):
    __tablename__ = 'subreddits'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    sort_method = db.Column(db.String(20), default='hot')  # hot, new, top, rising
    is_active = db.Column(db.Boolean, default=True)
    posts_per_visit = db.Column(db.Integer, default=20)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'sort_method': self.sort_method,
            'is_active': self.is_active,
            'posts_per_visit': self.posts_per_visit,
        }


class Keyword(db.Model):
    __tablename__ = 'keywords'

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(20), nullable=False)  # reddit, instagram, youtube
    keyword = db.Column(db.String(300), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'platform': self.platform,
            'keyword': self.keyword,
            'is_active': self.is_active,
        }


class CommentLog(db.Model):
    __tablename__ = 'comment_logs'

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(20), nullable=False)
    account_username = db.Column(db.String(100), nullable=False)
    post_url = db.Column(db.String(600), nullable=True)
    post_title = db.Column(db.String(600), nullable=True)
    subreddit = db.Column(db.String(100), nullable=True)
    search_keyword = db.Column(db.String(300), nullable=True)
    comment_text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # success, failed, pending, skipped
    error_message = db.Column(db.Text, nullable=True)
    match_score = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'platform': self.platform,
            'account_username': self.account_username,
            'post_url': self.post_url or '',
            'post_title': self.post_title or '',
            'subreddit': self.subreddit or '',
            'search_keyword': self.search_keyword or '',
            'comment_text': self.comment_text or '',
            'status': self.status,
            'error_message': self.error_message or '',
            'match_score': self.match_score,
            'created_at': self.created_at.isoformat(),
        }


class BotSettings(db.Model):
    __tablename__ = 'bot_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        setting = BotSettings.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        setting = BotSettings.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            setting = BotSettings(key=key, value=str(value))
            db.session.add(setting)
        db.session.commit()

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
        }


class BotSession(db.Model):
    __tablename__ = 'bot_sessions'

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(20), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    status = db.Column(db.String(20), default='started')  # started, running, stopped, error
    comments_made = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)

    account = db.relationship('Account', backref='sessions')

    def to_dict(self):
        return {
            'id': self.id,
            'platform': self.platform,
            'account_id': self.account_id,
            'status': self.status,
            'comments_made': self.comments_made,
            'started_at': self.started_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
        }
