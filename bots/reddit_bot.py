"""
Reddit web automation bot using Playwright.
Handles login, post scraping, and commenting through the browser.
"""

import logging
import time
import random
from datetime import datetime, timedelta
from typing import Optional
from threading import Event

from bots.base_bot import BaseBot

logger = logging.getLogger(__name__)

REDDIT_URL = "https://www.reddit.com"


class RedditBot(BaseBot):
    PLATFORM = 'reddit'

    def __init__(self, account: dict, headless: bool = True):
        super().__init__(account, headless)

    def login(self) -> bool:
        """Log into Reddit via browser."""
        try:
            self.page.goto(f"{REDDIT_URL}/login", wait_until='networkidle', timeout=30000)
            self.human_delay(2, 4)

            # Enter username
            username_input = self.page.locator('input[name="username"]')
            if username_input.count() == 0:
                # Try new Reddit login form
                username_input = self.page.locator('#login-username')

            username_input.fill('')
            self.human_delay(0.3, 0.6)
            username_input.type(self.account['username'], delay=random.randint(40, 90))
            self.human_delay(0.5, 1.0)

            # Enter password
            password_input = self.page.locator('input[name="password"]')
            if password_input.count() == 0:
                password_input = self.page.locator('#login-password')

            password_input.fill('')
            self.human_delay(0.3, 0.6)
            password_input.type(self.account['password'], delay=random.randint(40, 90))
            self.human_delay(0.5, 1.5)

            # Click login button
            login_btn = self.page.locator('button[type="submit"]')
            login_btn.click()

            # Wait for navigation
            self.page.wait_for_load_state('networkidle', timeout=15000)
            self.human_delay(3, 5)

            # Check if logged in by looking for user menu
            if self.page.locator('#USER_DROPDOWN_ID, button[id*="USER"], [data-testid="user-drawer-button"]').count() > 0:
                self.is_logged_in = True
                logger.info(f"[Reddit] Logged in as {self.username}")
                return True
            else:
                logger.warning(f"[Reddit] Login may have failed for {self.username}")
                self.take_screenshot('login_check')
                # Might still be logged in, proceed cautiously
                self.is_logged_in = True
                return True

        except Exception as e:
            logger.error(f"[Reddit] Login failed for {self.username}: {e}")
            self.take_screenshot('login_error')
            return False

    def find_posts(self, subreddit: str, sort_method: str = 'hot',
                   max_posts: int = 20) -> list[dict]:
        """
        Scrape posts from a subreddit.

        Args:
            subreddit: Subreddit name (without r/)
            sort_method: 'hot', 'new', 'top', 'rising'
            max_posts: Max number of posts to scrape

        Returns:
            List of post dicts with title, description, url keys
        """
        try:
            url = f"{REDDIT_URL}/r/{subreddit}/{sort_method}/"
            self.page.goto(url, wait_until='domcontentloaded', timeout=20000)
            self.human_delay(2, 4)

            # Scroll to load posts
            for _ in range(3):
                self.scroll_page('down', random.randint(400, 800))
                self.human_delay(1, 2)

            posts = []

            # Try to get posts using various selectors (Reddit changes layout often)
            post_selectors = [
                'shreddit-post',                    # New Reddit custom element
                'div[data-testid="post-container"]', # New Reddit
                '.Post',                              # Old-ish Reddit
                'article',                            # Generic
            ]

            post_elements = None
            for selector in post_selectors:
                elements = self.page.locator(selector)
                if elements.count() > 0:
                    post_elements = elements
                    break

            if not post_elements or post_elements.count() == 0:
                logger.warning(f"[Reddit] No posts found in r/{subreddit}")
                self.take_screenshot(f'no_posts_{subreddit}')
                return []

            count = min(post_elements.count(), max_posts)

            for i in range(count):
                try:
                    el = post_elements.nth(i)

                    # Extract title
                    title_el = el.locator('a[slot="title"], h3, [data-testid="post-title"], a[data-click-id="body"]')
                    title = title_el.first.inner_text() if title_el.count() > 0 else ''

                    # Extract link
                    link_el = el.locator('a[slot="title"], a[data-click-id="body"], a[href*="/comments/"]')
                    href = ''
                    if link_el.count() > 0:
                        href = link_el.first.get_attribute('href') or ''
                        if href.startswith('/'):
                            href = REDDIT_URL + href

                    # Extract description/body text
                    body_el = el.locator('[data-testid="post-body"], .RichTextJSON-root, div[slot="text-body"]')
                    description = body_el.first.inner_text() if body_el.count() > 0 else ''

                    if title and href:
                        posts.append({
                            'title': title.strip(),
                            'description': description.strip()[:1000],
                            'url': href,
                            'subreddit': subreddit,
                        })
                except Exception as e:
                    logger.debug(f"[Reddit] Error parsing post {i} in r/{subreddit}: {e}")
                    continue

            logger.info(f"[Reddit] Found {len(posts)} posts in r/{subreddit} ({sort_method})")
            return posts

        except Exception as e:
            logger.error(f"[Reddit] Error scraping r/{subreddit}: {e}")
            self.take_screenshot(f'scrape_error_{subreddit}')
            return []

    def post_comment(self, post_url: str, comment_text: str) -> bool:
        """
        Post a comment on a Reddit post via browser automation.

        Args:
            post_url: Full URL of the Reddit post
            comment_text: The comment to post

        Returns:
            True if comment was posted successfully
        """
        try:
            self.page.goto(post_url, wait_until='domcontentloaded', timeout=20000)
            self.human_delay(2, 4)

            # Random mouse movements for human mimicry
            self.random_mouse_movement()
            self.human_delay(0.5, 1.0)

            # Scroll down to comment area
            self.scroll_page('down', random.randint(200, 500))
            self.human_delay(1, 2)

            # Try to find and click the comment box
            comment_selectors = [
                'shreddit-composer',                        # New Reddit
                'div[contenteditable="true"]',              # Rich text editor
                'textarea[placeholder*="comment"]',         # Plain textarea
                'div[data-testid="comment-composer"]',      # Test ID
                '.public-DraftEditor-content',              # Draft.js editor
                'div[role="textbox"]',                      # Generic textbox
            ]

            comment_box = None
            for selector in comment_selectors:
                el = self.page.locator(selector)
                if el.count() > 0:
                    comment_box = el.first
                    break

            if not comment_box:
                logger.warning(f"[Reddit] Comment box not found on {post_url}")
                self.take_screenshot('no_comment_box')
                return False

            # Click to activate comment box
            comment_box.click()
            self.human_delay(0.5, 1.0)

            # Look for the actual input after clicking
            active_input = self.page.locator(
                'div[contenteditable="true"], textarea, div[role="textbox"], '
                '.public-DraftEditor-content div[data-contents="true"]'
            )

            if active_input.count() > 0:
                target = active_input.first
                target.click()
                self.human_delay(0.3, 0.5)

                # Type comment with human-like speed
                for i, char in enumerate(comment_text):
                    target.press_sequentially(char, delay=random.randint(20, 80))
                    if random.random() < 0.03:
                        time.sleep(random.uniform(0.2, 0.8))

            self.human_delay(1, 3)

            # Find and click submit button
            submit_selectors = [
                'button[type="submit"]:has-text("Comment")',
                'button:has-text("Comment")',
                'button[slot="submit-button"]',
                'button[data-testid="comment-submission-form-submit"]',
            ]

            submitted = False
            for selector in submit_selectors:
                btn = self.page.locator(selector)
                if btn.count() > 0:
                    btn.first.click()
                    submitted = True
                    break

            if not submitted:
                logger.warning(f"[Reddit] Submit button not found on {post_url}")
                self.take_screenshot('no_submit')
                return False

            self.human_delay(2, 4)
            self._comments_made += 1
            logger.info(f"[Reddit] Comment posted on {post_url[:80]} by {self.username}")
            return True

        except Exception as e:
            logger.error(f"[Reddit] Error commenting on {post_url}: {e}")
            self.take_screenshot('comment_error')
            return False


def run_reddit_bot(stop_event: Event, account: dict, subreddits: list[dict],
                   keywords: list[str], ai_generator, semantic_matcher,
                   daily_limit: int = 1000, min_delay: float = 30,
                   max_delay: float = 120, sort_method: str = 'hot',
                   posts_per_visit: int = 20, match_threshold: float = 0.45,
                   preprompt: str = '', ai_batch_size: int = 3,
                   ai_request_delay: float = 2.2, ai_batch_extra_prompt: str = '',
                   start_hour: int = 7, end_hour: int = 23,
                   headless: bool = True, db_session=None,
                   log_callback=None, task_id: str = '', state_store=None):
    """
    Main run loop for a single Reddit account bot instance.
    Called by the scheduler in a separate thread.
    """
    from core.comment_distributor import distribute_comments
    from core.scheduler import CommentScheduler

    bot = RedditBot(account, headless=headless)

    def emit_status(now_text: str, next_text: str = '', eta_seconds: float | None = None):
        if not log_callback:
            return
        eta_text = ''
        if eta_seconds is not None and eta_seconds > 0:
            eta_at = datetime.now() + timedelta(seconds=eta_seconds)
            eta_text = f" Next ETA: {int(eta_seconds)}s (~{eta_at.strftime('%H:%M:%S')})."
        details = (next_text + eta_text).strip()
        log_callback(
            'reddit', account['username'], '', now_text, details,
            'pending', '', 'system', None
        )

    try:
        bot.launch_browser()
        emit_status('Now: launching browser', 'Next: login to Reddit account')

        # Prepare semantic matching in the worker thread to keep the start API responsive.
        if keywords and semantic_matcher:
            try:
                semantic_matcher.set_keywords(keywords)
            except Exception as e:
                logger.error(f"[Reddit] Semantic matcher init failed: {e}")
                semantic_matcher = None

        if not bot.login():
            logger.error(f"[Reddit] Cannot start - login failed for {account['username']}")
            return
        emit_status('Now: logged in successfully', 'Next: gather candidate posts from subreddits')

        # Wait for schedule window if needed
        wait_secs, window_duration = CommentScheduler.time_until_window(start_hour, end_hour)
        if wait_secs > 0:
            logger.info(f"[Reddit] Waiting {wait_secs:.0f}s for schedule window")
            emit_status('Now: outside schedule window', 'Next: start posting when window opens', wait_secs)
            for _ in range(int(wait_secs)):
                if stop_event.is_set():
                    return
                time.sleep(1)

        # Track all URLs we've already commented on to avoid duplicates
        resume_state = account.get('resume_state') or {}
        commented_urls = set(resume_state.get('commented_urls', []))
        total_comments_target = daily_limit - account.get('comments_today', 0)
        sort_methods_cycle = ['hot', 'new', 'rising', 'top']
        max_rounds = 5  # Safety cap to prevent infinite loops
        current_round = int(resume_state.get('current_round', 0) or 0)
        current_match_threshold = match_threshold

        if commented_urls:
            logger.info(f"[Reddit] Restored checkpoint for {account['username']}: "
                        f"{len(commented_urls)} processed URLs, resuming from round {current_round + 1}")

        while bot.comments_made < total_comments_target and current_round < max_rounds:
            if stop_event.is_set():
                break

            current_round += 1
            remaining = total_comments_target - bot.comments_made
            if state_store and task_id:
                state_store.checkpoint(task_id, current_round=current_round)

            # --- Phase 1: Scrape and match posts ---
            # On subsequent rounds, try different sort methods and fetch more posts
            cycle_sort = sort_methods_cycle[(current_round - 1) % len(sort_methods_cycle)]
            scaled_posts_per_visit = min(posts_per_visit * current_round, 50)

            logger.info(f"[Reddit] Round {current_round}: Scraping posts "
                        f"(sort={cycle_sort}, per_sub={scaled_posts_per_visit}, "
                        f"threshold={current_match_threshold:.2f}, need {remaining} more)")
            emit_status(
                f"Now: round {current_round} scraping posts ({cycle_sort})",
                f"Next: semantic-match and allocate up to {remaining} comments"
            )

            subreddit_eligible = {}

            for sub_config in subreddits:
                if stop_event.is_set():
                    break

                sub_name = sub_config.get('name', '')
                # Use the configured sort on round 1, cycle through others after
                sub_sort = sub_config.get('sort_method', sort_method) if current_round == 1 else cycle_sort
                sub_posts = sub_config.get('posts_per_visit', posts_per_visit) if current_round == 1 else scaled_posts_per_visit

                posts = bot.find_posts(sub_name, sub_sort, sub_posts)
                bot.human_delay(2, 5)

                # Filter out already-commented posts
                posts = [p for p in posts if p.get('url') not in commented_urls]

                if keywords and semantic_matcher:
                    posts = semantic_matcher.batch_match(posts, threshold=current_match_threshold)
                    eligible = [p for p in posts if p.get('is_match', False)]
                else:
                    eligible = posts

                if eligible:
                    subreddit_eligible[sub_name] = eligible
                    logger.info(f"[Reddit] r/{sub_name}: {len(eligible)}/{len(posts)} new posts match")

            if not subreddit_eligible:
                if current_round == 1:
                    logger.warning("[Reddit] No eligible posts found across any subreddit")
                else:
                    logger.info(f"[Reddit] Round {current_round}: No new eligible posts found")
                # Relax threshold for next round to find more posts
                current_match_threshold = max(current_match_threshold - 0.1, 0.15)
                continue

            # --- Phase 2: Distribute comments ---
            allocation = distribute_comments(subreddit_eligible, remaining)

            total_allocated = sum(len(v) for v in allocation.values())
            if total_allocated == 0:
                current_match_threshold = max(current_match_threshold - 0.1, 0.15)
                continue

            logger.info(f"[Reddit] Round {current_round}: {total_allocated} comments allocated "
                        f"across {len(allocation)} subreddits")
            emit_status(
                f"Now: {total_allocated} comments allocated in round {current_round}",
                'Next: generate AI comments and post sequentially'
            )

            # --- Phase 3: Calculate delays ---
            _, window_remaining = CommentScheduler.time_until_window(start_hour, end_hour)
            delays = CommentScheduler.calculate_delays(
                total_allocated, window_remaining, min_delay, max_delay
            )

            # --- Phase 4: Post comments ---
            comment_queue = []
            for sub_name, posts in allocation.items():
                for post in posts:
                    comment_queue.append((sub_name, post))

            random.shuffle(comment_queue)

            for i in range(0, len(comment_queue), max(1, ai_batch_size)):
                if stop_event.is_set():
                    logger.info(f"[Reddit] Bot stopped by user")
                    break

                batch_pairs = comment_queue[i:i + max(1, ai_batch_size)]
                batch_inputs = []
                for sub_name, post in batch_pairs:
                    batch_inputs.append({
                        'title': post.get('title', ''),
                        'description': post.get('description', ''),
                        'subreddit': sub_name,
                    })

                try:
                    comments = ai_generator.generate_comments_batch(
                        posts=batch_inputs,
                        preprompt=preprompt,
                        platform='reddit',
                        extra_prompt=ai_batch_extra_prompt,
                        min_request_interval=ai_request_delay,
                    )
                except Exception as e:
                    logger.error(f"[Reddit] Batch AI generation failed: {e}")
                    comments = [''] * len(batch_pairs)

                for offset, (sub_name, post) in enumerate(batch_pairs):
                    if stop_event.is_set():
                        break

                    queue_index = i + offset
                    comment = comments[offset] if offset < len(comments) else ''
                    if not comment.strip():
                        err = 'AI batch response missing comment for post'
                        if log_callback:
                            log_callback('reddit', account['username'], post.get('url', ''),
                                         post.get('title', ''), '', 'failed', err, sub_name,
                                         post.get('match_score'))
                        continue

                    success = bot.post_comment(post['url'], comment)
                    commented_urls.add(post.get('url', ''))
                    if state_store and task_id:
                        state_store.checkpoint(
                            task_id,
                            processed_url=post.get('url', ''),
                            current_round=current_round,
                        )

                    status = 'success' if success else 'failed'
                    if log_callback:
                        log_callback('reddit', account['username'], post.get('url', ''),
                                     post['title'], comment, status, '', sub_name,
                                     post.get('match_score'))

                    if queue_index < len(delays):
                        delay = delays[queue_index]
                        emit_status(
                            f"Now: waiting before next Reddit comment ({sub_name})",
                            'Next: open next post and submit generated comment',
                            delay,
                        )
                        logger.debug(f"[Reddit] Waiting {delay:.1f}s before next comment")
                        for _ in range(int(delay)):
                            if stop_event.is_set():
                                break
                            time.sleep(1)
                        remaining_frac = delay - int(delay)
                        if remaining_frac > 0:
                            time.sleep(remaining_frac)

            if bot.comments_made < total_comments_target and not stop_event.is_set():
                logger.info(f"[Reddit] {bot.comments_made}/{total_comments_target} comments done, "
                            f"searching for more posts...")
                # Relax threshold slightly for next round
                current_match_threshold = max(current_match_threshold - 0.05, 0.15)

        logger.info(f"[Reddit] Bot finished. {bot.comments_made}/{total_comments_target} comments "
                     f"posted by {account['username']} in {current_round} round(s)")
        emit_status(
            f"Now: run finished ({bot.comments_made}/{total_comments_target} comments)",
            'Next: idle until next start request'
        )

        if state_store and task_id:
            if stop_event.is_set():
                state_store.mark_stopped(task_id, 'stopped')
            else:
                state_store.mark_completed(task_id)

    except Exception as e:
        logger.error(f"[Reddit] Bot error for {account['username']}: {e}", exc_info=True)
        if state_store and task_id:
            state_store.mark_error(task_id, str(e))
    finally:
        bot.close_browser()
