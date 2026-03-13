"""
Gemini AI comment generator.
Uses Google's Generative AI API to generate natural comments based on post content.
"""

import google.generativeai as genai
import logging
import time
import random

logger = logging.getLogger(__name__)


class GeminiAI:
    AVAILABLE_MODELS = [
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

    def generate_comment(self, post_title: str, post_description: str = '',
                         preprompt: str = '', platform: str = 'reddit',
                         subreddit: str = '', retries: int = 3) -> str:
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

        for attempt in range(retries):
            try:
                response = self.model.generate_content(prompt)
                comment = response.text.strip()
                # Clean up any wrapping quotes
                if comment.startswith('"') and comment.endswith('"'):
                    comment = comment[1:-1]
                if comment.startswith("'") and comment.endswith("'"):
                    comment = comment[1:-1]
                logger.info(f"Generated comment ({len(comment)} chars) for: {post_title[:50]}")
                return comment
            except Exception as e:
                logger.error(f"Gemini API error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait)

        raise RuntimeError(f"Failed to generate comment after {retries} attempts")

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
