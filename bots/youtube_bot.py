"""
YouTube web automation bot using Playwright.
Handles login, keyword search, and commenting through the browser.
"""

import logging
import time
import random
from datetime import datetime, timedelta
from threading import Event

from bots.base_bot import BaseBot

logger = logging.getLogger(__name__)

YOUTUBE_URL = "https://www.youtube.com"


class YouTubeBot(BaseBot):
    PLATFORM = 'youtube'

    def __init__(self, account: dict, headless: bool = True):
        super().__init__(account, headless)

    def login(self) -> bool:
        """Log into YouTube/Google via browser."""
        try:
            self.page.goto("https://accounts.google.com/signin",
                           wait_until='networkidle', timeout=30000)
            self.human_delay(2, 4)

            # Enter email
            email_input = self.page.locator('input[type="email"]')
            email_input.click()
            self.human_delay(0.3, 0.6)
            email_input.type(self.account.get('email', self.account['username']),
                             delay=random.randint(40, 90))
            self.human_delay(0.5, 1.0)

            # Click Next
            next_btn = self.page.locator('#identifierNext, button:has-text("Next")')
            next_btn.click()
            self.human_delay(2, 4)

            self.page.wait_for_load_state('networkidle', timeout=10000)

            # Enter password
            pass_input = self.page.locator('input[type="password"]')
            pass_input.click()
            self.human_delay(0.3, 0.6)
            pass_input.type(self.account['password'], delay=random.randint(40, 90))
            self.human_delay(0.5, 1.5)

            # Click Next
            next_btn2 = self.page.locator('#passwordNext, button:has-text("Next")')
            next_btn2.click()

            self.page.wait_for_load_state('networkidle', timeout=15000)
            self.human_delay(3, 5)

            # Navigate to YouTube to confirm login
            self.page.goto(YOUTUBE_URL, wait_until='domcontentloaded', timeout=20000)
            self.human_delay(2, 4)

            # Handle consent page if it appears
            agree_btn = self.page.locator(
                'button:has-text("Accept all"), button:has-text("I agree"), '
                'button[aria-label*="Accept"]'
            )
            if agree_btn.count() > 0:
                agree_btn.first.click()
                self.human_delay(2, 3)

            self.is_logged_in = True
            logger.info(f"[YouTube] Logged in as {self.username}")
            return True

        except Exception as e:
            logger.error(f"[YouTube] Login failed for {self.username}: {e}")
            self.take_screenshot('login_error')
            return False

    def search_videos(self, keyword: str, max_results: int = 10) -> list[dict]:
        """
        Search YouTube for videos matching a keyword.

        Args:
            keyword: Search term
            max_results: Max videos to return

        Returns:
            List of video dicts with url, title keys
        """
        try:
            search_url = f"{YOUTUBE_URL}/results?search_query={keyword.replace(' ', '+')}"
            self.page.goto(search_url, wait_until='domcontentloaded', timeout=20000)
            self.human_delay(2, 4)

            # Scroll to load results
            for _ in range(2):
                self.scroll_page('down', random.randint(300, 600))
                self.human_delay(1, 2)

            videos = []

            # Get video renderers
            video_elements = self.page.locator('ytd-video-renderer, ytd-rich-item-renderer')
            count = min(video_elements.count(), max_results)

            for i in range(count):
                try:
                    el = video_elements.nth(i)

                    # Get title and URL
                    title_link = el.locator('a#video-title, a[href*="watch?v="]')
                    if title_link.count() == 0:
                        continue

                    title = title_link.first.get_attribute('title') or title_link.first.inner_text()
                    href = title_link.first.get_attribute('href') or ''
                    if href.startswith('/'):
                        href = YOUTUBE_URL + href

                    if title and href and 'watch?v=' in href:
                        videos.append({
                            'url': href,
                            'title': title.strip(),
                            'description': '',
                            'search_keyword': keyword,
                        })
                except Exception:
                    continue

            logger.info(f"[YouTube] Found {len(videos)} videos for keyword '{keyword}'")
            return videos

        except Exception as e:
            logger.error(f"[YouTube] Search error for '{keyword}': {e}")
            self.take_screenshot(f'search_error_{keyword}')
            return []

    def post_comment(self, video_url: str, comment_text: str) -> bool:
        """Post a comment on a YouTube video."""
        try:
            self.page.goto(video_url, wait_until='domcontentloaded', timeout=20000)
            self.human_delay(3, 5)

            # Scroll down to load comment section
            for _ in range(3):
                self.scroll_page('down', random.randint(300, 500))
                self.human_delay(1, 2)

            self.random_mouse_movement()

            # Click on comment placeholder to activate input
            comment_placeholder = self.page.locator(
                '#simplebox-placeholder, '
                'ytd-comment-simplebox-renderer #placeholder-area, '
                'tp-yt-paper-input-container'
            )

            if comment_placeholder.count() > 0:
                comment_placeholder.first.click()
                self.human_delay(1, 2)
            else:
                logger.warning(f"[YouTube] Comment placeholder not found on {video_url}")
                self.take_screenshot('no_comment_placeholder')
                return False

            # Find the active comment input
            comment_input = self.page.locator(
                '#contenteditable-root, '
                'div[contenteditable="true"][id="contenteditable-root"], '
                'ytd-comment-simplebox-renderer div[contenteditable="true"]'
            )

            if comment_input.count() == 0:
                logger.warning(f"[YouTube] Comment input not found on {video_url}")
                self.take_screenshot('no_comment_input')
                return False

            input_el = comment_input.first
            input_el.click()
            self.human_delay(0.5, 1.0)

            # Type comment with human speed
            for char in comment_text:
                input_el.press_sequentially(char, delay=random.randint(20, 70))
                if random.random() < 0.03:
                    time.sleep(random.uniform(0.2, 0.6))

            self.human_delay(1, 3)

            # Click submit
            submit_btn = self.page.locator(
                '#submit-button, '
                'ytd-comment-simplebox-renderer #submit-button, '
                'button[aria-label*="Comment" i]'
            )

            if submit_btn.count() > 0:
                submit_btn.first.click()
            else:
                logger.warning(f"[YouTube] Submit button not found on {video_url}")
                self.take_screenshot('no_submit')
                return False

            self.human_delay(2, 4)
            self._comments_made += 1
            logger.info(f"[YouTube] Comment posted on {video_url[:60]} by {self.username}")
            return True

        except Exception as e:
            logger.error(f"[YouTube] Error commenting on {video_url}: {e}")
            self.take_screenshot('comment_error')
            return False

    def get_video_info(self) -> dict:
        """Extract video title and description from current page."""
        info = {'title': '', 'description': ''}
        try:
            title_el = self.page.locator(
                'h1.ytd-watch-metadata yt-formatted-string, '
                'h1.title yt-formatted-string'
            )
            if title_el.count() > 0:
                info['title'] = title_el.first.inner_text()[:300]

            # Expand description if needed
            expand_btn = self.page.locator(
                'tp-yt-paper-button#expand, #description-inline-expander'
            )
            if expand_btn.count() > 0:
                try:
                    expand_btn.first.click()
                    self.human_delay(0.5, 1.0)
                except Exception:
                    pass

            desc_el = self.page.locator(
                '#description-inline-expander yt-formatted-string, '
                '#description yt-formatted-string'
            )
            if desc_el.count() > 0:
                info['description'] = desc_el.first.inner_text()[:500]

        except Exception:
            pass
        return info


def run_youtube_bot(stop_event: Event, account: dict, search_keywords: list[str],
                    ai_generator, daily_limit: int = 1000,
                    min_delay: float = 30, max_delay: float = 120,
                    preprompt: str = '', start_hour: int = 7, end_hour: int = 23,
                    ai_batch_size: int = 3, ai_request_delay: float = 2.2,
                    ai_batch_extra_prompt: str = '',
                    headless: bool = True, log_callback=None,
                    task_id: str = '', state_store=None):
    """
    Main run loop for a single YouTube account bot.
    """
    from core.comment_distributor import distribute_comments
    from core.scheduler import CommentScheduler

    bot = YouTubeBot(account, headless=headless)

    def emit_status(now_text: str, next_text: str = '', eta_seconds: float | None = None):
        if not log_callback:
            return
        eta_text = ''
        if eta_seconds is not None and eta_seconds > 0:
            eta_at = datetime.now() + timedelta(seconds=eta_seconds)
            eta_text = f" Next ETA: {int(eta_seconds)}s (~{eta_at.strftime('%H:%M:%S')})."
        details = (next_text + eta_text).strip()
        log_callback(
            'youtube', account['username'], '', now_text, details,
            'pending', '', 'system', None
        )

    try:
        bot.launch_browser()
        emit_status('Now: launching browser', 'Next: login to YouTube account')

        if not bot.login():
            logger.error(f"[YouTube] Cannot start - login failed for {account['username']}")
            return
        emit_status('Now: logged in successfully', 'Next: search videos by configured keywords')

        # Wait for window
        wait_secs, _ = CommentScheduler.time_until_window(start_hour, end_hour)
        if wait_secs > 0:
            logger.info(f"[YouTube] Waiting {wait_secs:.0f}s for schedule window")
            emit_status('Now: outside schedule window', 'Next: start posting when window opens', wait_secs)
            for _ in range(int(wait_secs)):
                if stop_event.is_set():
                    return
                time.sleep(1)

        # --- Scrape and comment in rounds until daily limit is hit ---
        resume_state = account.get('resume_state') or {}
        commented_urls = set(resume_state.get('commented_urls', []))
        total_comments_target = daily_limit - account.get('comments_today', 0)
        max_rounds = 5
        current_round = int(resume_state.get('current_round', 0) or 0)

        if commented_urls:
            logger.info(f"[YouTube] Restored checkpoint for {account['username']}: "
                        f"{len(commented_urls)} processed URLs, resuming from round {current_round + 1}")

        while bot.comments_made < total_comments_target and current_round < max_rounds:
            if stop_event.is_set():
                break

            current_round += 1
            remaining = total_comments_target - bot.comments_made
            if state_store and task_id:
                state_store.checkpoint(task_id, current_round=current_round)

            # Scale up results per keyword on subsequent rounds
            scaled_per_keyword = max(5, (30 * current_round) // max(len(search_keywords), 1))

            logger.info(f"[YouTube] Round {current_round}: Searching videos "
                        f"(per_keyword={scaled_per_keyword}, need {remaining} more)")
            emit_status(
                f"Now: round {current_round} searching videos",
                f"Next: allocate and post up to {remaining} comments"
            )

            keyword_videos = {}
            for kw in search_keywords:
                if stop_event.is_set():
                    break
                videos = bot.search_videos(kw, max_results=scaled_per_keyword)
                # Filter out already-commented videos
                videos = [v for v in videos if v.get('url') not in commented_urls]
                if videos:
                    keyword_videos[kw] = videos
                bot.human_delay(3, 6)

            if not keyword_videos:
                if current_round == 1:
                    logger.warning("[YouTube] No videos found for any keyword")
                else:
                    logger.info(f"[YouTube] Round {current_round}: No new videos found")
                continue

            # --- Distribute across keywords ---
            allocation = distribute_comments(keyword_videos, remaining)
            total = sum(len(v) for v in allocation.values())

            if total == 0:
                continue

            logger.info(f"[YouTube] Round {current_round}: {total} comments allocated")
            emit_status(
                f"Now: {total} comments allocated in round {current_round}",
                'Next: generate AI comments and post them'
            )

            # --- Schedule and post ---
            _, window_remaining = CommentScheduler.time_until_window(start_hour, end_hour)
            delays = CommentScheduler.calculate_delays(total, window_remaining, min_delay, max_delay)

            comment_queue = []
            for kw, videos in allocation.items():
                for video in videos:
                    comment_queue.append((kw, video))
            random.shuffle(comment_queue)

            for i in range(0, len(comment_queue), max(1, ai_batch_size)):
                if stop_event.is_set():
                    break

                batch_pairs = comment_queue[i:i + max(1, ai_batch_size)]
                batch_inputs = []
                nav_failures = []

                for kw, video in batch_pairs:
                    try:
                        bot.page.goto(video['url'], wait_until='domcontentloaded', timeout=20000)
                        bot.human_delay(2, 4)
                        info = bot.get_video_info()
                        batch_inputs.append({
                            'title': info.get('title', video.get('title', kw)),
                            'description': info.get('description', ''),
                            'subreddit': '',
                        })
                        nav_failures.append('')
                    except Exception as e:
                        batch_inputs.append({'title': video.get('title', kw), 'description': '', 'subreddit': ''})
                        nav_failures.append(str(e))

                try:
                    comments = ai_generator.generate_comments_batch(
                        posts=batch_inputs,
                        preprompt=preprompt,
                        platform='youtube',
                        extra_prompt=ai_batch_extra_prompt,
                        min_request_interval=ai_request_delay,
                    )
                except Exception as e:
                    logger.error(f"[YouTube] Batch AI generation failed: {e}")
                    comments = [''] * len(batch_pairs)

                for offset, (kw, video) in enumerate(batch_pairs):
                    if stop_event.is_set():
                        break

                    queue_index = i + offset
                    if nav_failures[offset]:
                        if log_callback:
                            log_callback('youtube', account['username'], video['url'],
                                         video['title'], '', 'failed', nav_failures[offset], kw, None)
                        continue

                    comment = comments[offset] if offset < len(comments) else ''
                    if not comment.strip():
                        if log_callback:
                            log_callback('youtube', account['username'], video['url'],
                                         video['title'], '', 'failed',
                                         'AI batch response missing comment for video', kw, None)
                        continue

                    success = bot.post_comment(video['url'], comment)
                    commented_urls.add(video.get('url', ''))
                    if state_store and task_id:
                        state_store.checkpoint(
                            task_id,
                            processed_url=video.get('url', ''),
                            current_round=current_round,
                        )
                    status = 'success' if success else 'failed'

                    if log_callback:
                        log_callback('youtube', account['username'], video['url'],
                                     video['title'], comment, status, '', kw, None)

                    if queue_index < len(delays):
                        delay = delays[queue_index]
                        emit_status(
                            f"Now: waiting before next YouTube comment ({kw})",
                            'Next: open next video and submit generated comment',
                            delay,
                        )
                        for _ in range(int(delay)):
                            if stop_event.is_set():
                                break
                            time.sleep(1)

            if bot.comments_made < total_comments_target and not stop_event.is_set():
                logger.info(f"[YouTube] {bot.comments_made}/{total_comments_target} comments done, "
                            f"searching for more videos...")

        logger.info(f"[YouTube] Bot finished. {bot.comments_made}/{total_comments_target} comments "
                     f"by {account['username']} in {current_round} round(s)")
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
        logger.error(f"[YouTube] Bot error for {account['username']}: {e}", exc_info=True)
        if state_store and task_id:
            state_store.mark_error(task_id, str(e))
    finally:
        bot.close_browser()
