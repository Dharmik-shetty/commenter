import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'data', 'bot.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Gemini AI defaults
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
    GEMINI_TEMPERATURE = 0.9
    GEMINI_MAX_TOKENS = 300
    GEMINI_TOP_P = 0.95
    GEMINI_TOP_K = 40
    GEMINI_BATCH_SIZE = int(os.environ.get('GEMINI_BATCH_SIZE', 3))
    GEMINI_REQUEST_DELAY = float(os.environ.get('GEMINI_REQUEST_DELAY', 2.2))
    GEMINI_BATCH_EXTRA_PROMPT = os.environ.get(
        'GEMINI_BATCH_EXTRA_PROMPT',
        "Generate one distinct comment for every listed post. Keep output aligned by index.",
    )

    DEFAULT_PREPROMPT = (
        "You are a genuine Reddit user who is knowledgeable about fitness and health. "
        "Write a natural, conversational comment that adds value to the discussion. "
        "Keep it concise (1-3 sentences). Do NOT sound like a bot or use overly formal language. "
        "If relevant, subtly mention an AI fitness app you've been using without being pushy. "
        "Match the tone and style of the subreddit community. Do not use hashtags on Reddit."
    )

    INSTAGRAM_PREPROMPT = (
        "You are a fitness enthusiast on Instagram. Write a natural, engaging comment "
        "on this post. Keep it concise (1-2 sentences). Use 1-2 relevant emojis max. "
        "If appropriate, mention your experience with an AI-powered fitness app. "
        "Sound genuine and enthusiastic, not salesy."
    )

    YOUTUBE_PREPROMPT = (
        "You are a fitness enthusiast commenting on a YouTube video. Write a natural, "
        "engaging comment (1-3 sentences). Reference something specific from the video. "
        "If relevant, briefly mention an AI fitness app that helped you. "
        "Be conversational and add value to the discussion."
    )

    # Scheduling defaults
    DEFAULT_MIN_DELAY = 30       # seconds
    DEFAULT_MAX_DELAY = 120      # seconds
    DEFAULT_DAILY_LIMIT = 1000
    DEFAULT_START_HOUR = 7       # 7 AM
    DEFAULT_END_HOUR = 23        # 11 PM

    # Reddit defaults
    DEFAULT_SORT_METHOD = 'hot'
    DEFAULT_POSTS_PER_VISIT = 20
    DEFAULT_MATCH_THRESHOLD = 0.45

    # Concurrency defaults
    DEFAULT_MAX_CONCURRENT = 5       # Total accounts running at once across all platforms
    DEFAULT_CONCURRENT_REDDIT = 3    # Max Reddit accounts in parallel
    DEFAULT_CONCURRENT_INSTAGRAM = 1 # Max Instagram accounts in parallel
    DEFAULT_CONCURRENT_YOUTUBE = 1   # Max YouTube accounts in parallel

    # Semantic model
    SEMANTIC_MODEL = 'all-MiniLM-L6-v2'

    # Encryption key for stored passwords
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '')
