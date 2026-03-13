"""
Instagram web automation bot using Playwright.
Handles login, keyword search, and commenting through the browser.
"""

import logging
import time
import random
from threading import Event

from bots.base_bot import BaseBot

logger = logging.getLogger(__name__)

INSTAGRAM_URL = "https://www.instagram.com"


class InstagramBot(BaseBot):
    PLATFORM = 'instagram'

    def __init__(self, account: dict, headless: bool = True):
        super().__init__(account, headless)

    def login(self) -> bool:
        """Log into Instagram via browser."""
        try:
            self.page.goto(f"{INSTAGRAM_URL}/accounts/login/",
                           wait_until='networkidle', timeout=30000)
            self.human_delay(3, 5)

            # Handle cookie consent
            cookie_btn = self.page.locator('button:has-text("Allow"), button:has-text("Accept")')
            if cookie_btn.count() > 0:
                cookie_btn.first.click()
                self.human_delay(1, 2)

            # Enter username
            user_input = self.page.locator('input[name="username"]')
            user_input.click()
            self.human_delay(0.3, 0.6)
            user_input.type(self.account['username'], delay=random.randint(40, 90))
            self.human_delay(0.5, 1.0)

            # Enter password
            pass_input = self.page.locator('input[name="password"]')
            pass_input.click()
            self.human_delay(0.3, 0.6)
            pass_input.type(self.account['password'], delay=random.randint(40, 90))
            self.human_delay(0.5, 1.5)

            # Click login
            login_btn = self.page.locator('button[type="submit"]')
            login_btn.click()

            self.page.wait_for_load_state('networkidle', timeout=15000)
            self.human_delay(3, 6)

            # Handle "Save Login Info" dialog
            not_now = self.page.locator('button:has-text("Not Now"), button:has-text("Not now")')
            if not_now.count() > 0:
                not_now.first.click()
                self.human_delay(1, 2)

            # Handle "Turn on Notifications" dialog
            not_now2 = self.page.locator('button:has-text("Not Now"), button:has-text("Not now")')
            if not_now2.count() > 0:
                not_now2.first.click()
                self.human_delay(1, 2)

            self.is_logged_in = True
            logger.info(f"[Instagram] Logged in as {self.username}")
            return True

        except Exception as e:
            logger.error(f"[Instagram] Login failed for {self.username}: {e}")
            self.take_screenshot('login_error')
            return False

    def search_posts(self, keyword: str, max_posts: int = 10) -> list[dict]:
        """
        Search Instagram for posts matching a keyword.

        Args:
            keyword: Search term
            max_posts: Maximum posts to return

        Returns:
            List of post dicts with url and title keys
        """
        try:
            search_url = f"{INSTAGRAM_URL}/explore/tags/{keyword.replace(' ', '')}/"
            self.page.goto(search_url, wait_until='domcontentloaded', timeout=20000)
            self.human_delay(3, 5)

            # Scroll to load more posts
            for _ in range(2):
                self.scroll_page('down', random.randint(300, 600))
                self.human_delay(1, 3)

            posts = []

            # Get post links from the explore/tag grid
            post_links = self.page.locator('a[href*="/p/"], a[href*="/reel/"]')
            count = min(post_links.count(), max_posts)

            for i in range(count):
                try:
                    href = post_links.nth(i).get_attribute('href') or ''
                    if href.startswith('/'):
                        href = INSTAGRAM_URL + href

                    posts.append({
                        'url': href,
                        'title': keyword,
                        'description': '',
                        'search_keyword': keyword,
                    })
                except Exception:
                    continue

            logger.info(f"[Instagram] Found {len(posts)} posts for keyword '{keyword}'")
            return posts

        except Exception as e:
            logger.error(f"[Instagram] Search error for '{keyword}': {e}")
            self.take_screenshot(f'search_error_{keyword}')
            return []

    def post_comment(self, post_url: str, comment_text: str) -> bool:
        """Post a comment on an Instagram post."""
        try:
            self.page.goto(post_url, wait_until='domcontentloaded', timeout=20000)
            self.human_delay(2, 4)

            self.random_mouse_movement()
            self.human_delay(0.5, 1.0)

            # Get post caption for AI context
            caption = ''
            caption_el = self.page.locator('div[class*="Caption"] span, span[class*="_a9zs"]')
            if caption_el.count() > 0:
                caption = caption_el.first.inner_text()[:500]

            # Find comment textarea
            comment_selectors = [
                'textarea[placeholder*="comment" i]',
                'textarea[aria-label*="comment" i]',
                'form textarea',
                'textarea',
            ]

            comment_box = None
            for selector in comment_selectors:
                el = self.page.locator(selector)
                if el.count() > 0:
                    comment_box = el.first
                    break

            if not comment_box:
                # Try clicking the comment icon first
                comment_icon = self.page.locator(
                    'svg[aria-label*="Comment" i], button:has(svg[aria-label*="Comment" i])'
                )
                if comment_icon.count() > 0:
                    comment_icon.first.click()
                    self.human_delay(1, 2)

                for selector in comment_selectors:
                    el = self.page.locator(selector)
                    if el.count() > 0:
                        comment_box = el.first
                        break

            if not comment_box:
                logger.warning(f"[Instagram] Comment box not found on {post_url}")
                self.take_screenshot('no_comment_box')
                return False

            comment_box.click()
            self.human_delay(0.5, 1.0)

            # Type comment
            comment_box.fill('')
            for char in comment_text:
                comment_box.press_sequentially(char, delay=random.randint(20, 70))
                if random.random() < 0.03:
                    time.sleep(random.uniform(0.2, 0.6))

            self.human_delay(1, 2)

            # Submit
            submit_selectors = [
                'button[type="submit"]:has-text("Post")',
                'button:has-text("Post")',
                'div[role="button"]:has-text("Post")',
            ]

            submitted = False
            for selector in submit_selectors:
                btn = self.page.locator(selector)
                if btn.count() > 0:
                    btn.first.click()
                    submitted = True
                    break

            if not submitted:
                # Try pressing Enter
                comment_box.press('Enter')
                submitted = True

            self.human_delay(2, 4)
            self._comments_made += 1
            logger.info(f"[Instagram] Comment posted on {post_url[:60]} by {self.username}")
            return True

        except Exception as e:
            logger.error(f"[Instagram] Error commenting on {post_url}: {e}")
            self.take_screenshot('comment_error')
            return False

    def get_post_caption(self, post_url: str) -> str:
        """Get the caption text from an Instagram post (already navigated)."""
        try:
            caption_el = self.page.locator(
                'div[class*="Caption"] span, span[class*="_a9zs"], '
                'h1, div[class*="C4VMK"] span'
            )
            if caption_el.count() > 0:
                return caption_el.first.inner_text()[:500]
        except Exception:
            pass
        return ''


def run_instagram_bot(stop_event: Event, account: dict, search_keywords: list[str],
                      ai_generator, daily_limit: int = 1000,
                      min_delay: float = 30, max_delay: float = 120,
                      preprompt: str = '', start_hour: int = 7, end_hour: int = 23,
                      headless: bool = True, log_callback=None):
    """
    Main run loop for a single Instagram account bot.
    """
    from core.comment_distributor import distribute_comments
    from core.scheduler import CommentScheduler

    bot = InstagramBot(account, headless=headless)

    try:
        bot.launch_browser()

        if not bot.login():
            logger.error(f"[Instagram] Cannot start - login failed for {account['username']}")
            return

        # Wait for window
        wait_secs, window_duration = CommentScheduler.time_until_window(start_hour, end_hour)
        if wait_secs > 0:
            logger.info(f"[Instagram] Waiting {wait_secs:.0f}s for schedule window")
            for _ in range(int(wait_secs)):
                if stop_event.is_set():
                    return
                time.sleep(1)

        # --- Scrape and comment in rounds until daily limit is hit ---
        commented_urls = set()
        total_comments_target = daily_limit - account.get('comments_today', 0)
        max_rounds = 5
        current_round = 0

        while bot.comments_made < total_comments_target and current_round < max_rounds:
            if stop_event.is_set():
                break

            current_round += 1
            remaining = total_comments_target - bot.comments_made

            # Scale up results per keyword on subsequent rounds
            scaled_per_keyword = max(5, (30 * current_round) // max(len(search_keywords), 1))

            logger.info(f"[Instagram] Round {current_round}: Searching posts "
                        f"(per_keyword={scaled_per_keyword}, need {remaining} more)")

            keyword_posts = {}
            for kw in search_keywords:
                if stop_event.is_set():
                    break
                posts = bot.search_posts(kw, max_posts=scaled_per_keyword)
                # Filter out already-commented posts
                posts = [p for p in posts if p.get('url') not in commented_urls]
                if posts:
                    keyword_posts[kw] = posts
                bot.human_delay(3, 6)

            if not keyword_posts:
                if current_round == 1:
                    logger.warning("[Instagram] No posts found for any keyword")
                else:
                    logger.info(f"[Instagram] Round {current_round}: No new posts found")
                continue

            # --- Distribute across keywords ---
            allocation = distribute_comments(keyword_posts, remaining)
            total = sum(len(v) for v in allocation.values())

            if total == 0:
                continue

            logger.info(f"[Instagram] Round {current_round}: {total} comments allocated")

            # --- Schedule and post ---
            _, window_remaining = CommentScheduler.time_until_window(start_hour, end_hour)
            delays = CommentScheduler.calculate_delays(total, window_remaining, min_delay, max_delay)

            comment_queue = []
            for kw, posts in allocation.items():
                for post in posts:
                    comment_queue.append((kw, post))
            random.shuffle(comment_queue)

            for i, (kw, post) in enumerate(comment_queue):
                if stop_event.is_set():
                    break

                try:
                    # Navigate to post to get caption for AI context
                    bot.page.goto(post['url'], wait_until='domcontentloaded', timeout=20000)
                    bot.human_delay(2, 3)
                    caption = bot.get_post_caption(post['url'])

                    comment = ai_generator.generate_comment(
                        post_title=caption or kw,
                        post_description=caption,
                        preprompt=preprompt,
                        platform='instagram',
                    )
                except Exception as e:
                    logger.error(f"[Instagram] AI generation failed: {e}")
                    if log_callback:
                        log_callback('instagram', account['username'], post['url'],
                                     kw, '', 'failed', str(e), kw, None)
                    continue

                success = bot.post_comment(post['url'], comment)
                commented_urls.add(post.get('url', ''))
                status = 'success' if success else 'failed'

                if log_callback:
                    log_callback('instagram', account['username'], post['url'],
                                 kw, comment, status, '', kw, None)

                if i < len(delays):
                    delay = delays[i]
                    for _ in range(int(delay)):
                        if stop_event.is_set():
                            break
                        time.sleep(1)

            if bot.comments_made < total_comments_target and not stop_event.is_set():
                logger.info(f"[Instagram] {bot.comments_made}/{total_comments_target} comments done, "
                            f"searching for more posts...")

        logger.info(f"[Instagram] Bot finished. {bot.comments_made}/{total_comments_target} comments "
                     f"by {account['username']} in {current_round} round(s)")

    except Exception as e:
        logger.error(f"[Instagram] Bot error for {account['username']}: {e}", exc_info=True)
    finally:
        bot.close_browser()
