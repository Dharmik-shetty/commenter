"""
Gemini AI comment generator.
Uses Google's Generative AI API to generate natural comments based on post content.
"""

import google.generativeai as genai
import logging
import time
import random
import json
import re
import threading

logger = logging.getLogger(__name__)


class GeminiAI:
    AVAILABLE_MODELS = [
        'gemini-3.1-flash-lite',
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
    ]

    def __init__(self, api_key: str, model_name: str = 'gemini-2.0-flash',
                 temperature: float = 0.9, max_tokens: int = 300,
                 top_p: float = 0.95, top_k: int = 40):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.top_k = top_k
        self.model = None
        self._request_lock = threading.Lock()
        self._last_request_ts = 0.0
        self._configure()

    def _configure(self):
        if not self.api_key:
            logger.warning("Gemini API key not set")
            return
        genai.configure(api_key=self.api_key)
        generation_config = genai.types.GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            top_p=self.top_p,
            top_k=self.top_k,
        )
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=generation_config,
        )
        logger.info(f"Gemini AI configured with model: {self.model_name}")

    def update_config(self, **kwargs):
        for key in ['api_key', 'model_name', 'temperature', 'max_tokens', 'top_p', 'top_k']:
            if key in kwargs:
                setattr(self, key, kwargs[key])
        self._configure()

    def _apply_request_delay(self, min_request_interval: float):
        if min_request_interval <= 0:
            return
        with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_ts
            if elapsed < min_request_interval:
                wait = min_request_interval - elapsed
                time.sleep(wait)
            self._last_request_ts = time.time()

    def _generate_with_retries(self, prompt: str, retries: int = 3,
                               min_request_interval: float = 0.0) -> str:
        for attempt in range(retries):
            try:
                self._apply_request_delay(min_request_interval)
                response = self.model.generate_content(prompt)
                text = (response.text or '').strip()
                if not text:
                    raise RuntimeError('Empty response from Gemini')
                return text
            except Exception as e:
                logger.error(f"Gemini API error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait)
        raise RuntimeError(f"Failed to generate content after {retries} attempts")

    @staticmethod
    def _strip_wrapping_quotes(comment: str) -> str:
        comment = (comment or '').strip()
        if comment.startswith('"') and comment.endswith('"') and len(comment) >= 2:
            comment = comment[1:-1].strip()
        if comment.startswith("'") and comment.endswith("'") and len(comment) >= 2:
            comment = comment[1:-1].strip()
        return comment

    @staticmethod
    def _extract_json_blob(text: str) -> str:
        text = text.strip()

        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, flags=re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]

        return text

    def _parse_batch_comments(self, raw_text: str, expected_count: int) -> list[str]:
        parsed_comments = []

        try:
            json_blob = self._extract_json_blob(raw_text)
            data = json.loads(json_blob)
            comments = data.get('comments', []) if isinstance(data, dict) else []
            if isinstance(comments, list):
                indexed = {}
                for item in comments:
                    if not isinstance(item, dict):
                        continue
                    idx = item.get('index')
                    comment_text = item.get('comment', '')
                    if isinstance(idx, int) and 0 <= idx < expected_count:
                        indexed[idx] = self._strip_wrapping_quotes(str(comment_text))
                parsed_comments = [indexed.get(i, '') for i in range(expected_count)]
        except Exception:
            parsed_comments = []

        if parsed_comments and any(parsed_comments):
            return parsed_comments

        # Fallback parser: try line format "<index>: <comment>"
        fallback = [''] * expected_count
        for line in raw_text.splitlines():
            m = re.match(r"^\s*(\d+)\s*[:\-]\s*(.+)$", line.strip())
            if not m:
                continue
            idx = int(m.group(1))
            if 0 <= idx < expected_count:
                fallback[idx] = self._strip_wrapping_quotes(m.group(2))

        if any(fallback):
            return fallback

        return [''] * expected_count

    def generate_comment(self, post_title: str, post_description: str = '',
                         preprompt: str = '', platform: str = 'reddit',
                         subreddit: str = '', retries: int = 3,
                         min_request_interval: float = 0.0) -> str:
        """
        Generate a comment for a post using Gemini AI.

        Args:
            post_title: Title of the post
            post_description: Description/body of the post
            preprompt: System instruction for comment style
            platform: Platform name (reddit, instagram, youtube)
            subreddit: Subreddit name (for Reddit posts)
            retries: Number of retry attempts on failure

        Returns:
            Generated comment text
        """
        if not self.model:
            raise ValueError("Gemini AI not configured. Set API key first.")

        context_parts = [preprompt, f"\n--- {platform.upper()} POST ---"]

        if subreddit:
            context_parts.append(f"Subreddit: r/{subreddit}")

        context_parts.append(f"Title: {post_title}")

        if post_description:
            desc = post_description[:2000]  # Limit description length
            context_parts.append(f"Description: {desc}")

        context_parts.append(
            f"\n--- TASK ---\nWrite a single natural comment for this {platform} post. "
            "Return ONLY the comment text, nothing else. No quotes, no labels, no prefixes."
        )

        prompt = "\n".join(context_parts)

        comment = self._generate_with_retries(
            prompt,
            retries=retries,
            min_request_interval=min_request_interval,
        )
        comment = self._strip_wrapping_quotes(comment)
        logger.info(f"Generated comment ({len(comment)} chars) for: {post_title[:50]}")
        return comment

    def generate_comments_batch(self, posts: list[dict], preprompt: str = '',
                                platform: str = 'reddit', extra_prompt: str = '',
                                retries: int = 3,
                                min_request_interval: float = 0.0) -> list[str]:
        """
        Generate comments for multiple posts in a single Gemini request.

        Args:
            posts: List of dicts with keys: title, description, subreddit
            preprompt: Base writing instruction
            platform: Platform name
            extra_prompt: Extra batching instruction
            retries: Retry count
            min_request_interval: Minimum delay between Gemini requests

        Returns:
            List of generated comments aligned by input post order.
        """
        if not self.model:
            raise ValueError("Gemini AI not configured. Set API key first.")
        if not posts:
            return []

        lines = [preprompt.strip() if preprompt else '']
        lines.append(
            "You will receive multiple posts. Generate one natural comment for EACH post. "
            "Output must be strict JSON only."
        )
        if extra_prompt:
            lines.append(extra_prompt.strip())

        lines.append(f"\n--- {platform.upper()} POSTS ---")
        for idx, post in enumerate(posts):
            lines.append(f"\n[POST {idx}]")
            subreddit = (post.get('subreddit') or '').strip()
            if subreddit:
                lines.append(f"Subreddit: r/{subreddit}")
            lines.append(f"Title: {(post.get('title') or '').strip()}")
            desc = (post.get('description') or '').strip()
            if desc:
                lines.append(f"Description: {desc[:2000]}")

        lines.append(
            "\n--- OUTPUT FORMAT (STRICT) ---\n"
            "Return ONLY valid JSON, no markdown, no code block, no extra text.\n"
            "Schema:\n"
            "{\n"
            "  \"comments\": [\n"
            "    {\"index\": 0, \"comment\": \"...\"}\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- Include exactly one item per post index (0..N-1).\n"
            "- Keep comments concise and human (1-3 sentences unless instructed).\n"
            "- No labels, no hashtags unless platform style requires it."
        )

        prompt = "\n".join(lines)
        raw = self._generate_with_retries(
            prompt,
            retries=retries,
            min_request_interval=min_request_interval,
        )
        comments = self._parse_batch_comments(raw, len(posts))

        # Fill missing comments with safe fallback to keep pipeline aligned.
        for i in range(len(comments)):
            if not comments[i]:
                comments[i] = "Great post, thanks for sharing this."

        logger.info(f"Generated batch comments: {len(comments)} items for {platform}")
        return comments

    def test_connection(self) -> bool:
        """Test if the Gemini API connection works."""
        try:
            if not self.model:
                return False
            response = self.model.generate_content("Say 'OK' if you can read this.")
            return bool(response.text)
        except Exception as e:
            logger.error(f"Gemini connection test failed: {e}")
            return False
