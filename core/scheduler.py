"""
Comment scheduler with human-like random delays.
Manages running bot instances across multiple accounts and platforms.
"""

import random
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CommentScheduler:
    """
    Schedules and executes comment tasks with random delays
    within a configurable time window to mimic human behavior.
    Supports global concurrency limits to control resource usage.
    """

    def __init__(self):
        self._threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._status: dict[str, str] = {}  # running, stopped, error
        self._lock = threading.Lock()
        self._concurrency_semaphore: Optional[threading.Semaphore] = None
        self._max_concurrent: int = 0
        self._queued_tasks: list[tuple] = []  # Tasks waiting for a slot
        self._queue_lock = threading.Lock()

    def set_concurrency_limit(self, max_concurrent: int):
        """Set the maximum number of tasks that can run simultaneously."""
        self._max_concurrent = max_concurrent
        if max_concurrent > 0:
            self._concurrency_semaphore = threading.Semaphore(max_concurrent)
        else:
            self._concurrency_semaphore = None
        logger.info(f"Concurrency limit set to: {max_concurrent or 'unlimited'}")

    @staticmethod
    def calculate_delays(num_comments: int, window_seconds: float,
                         min_delay: float = 30, max_delay: float = 120) -> list[float]:
        """
        Calculate a list of random delays for posting comments
        that fit within the given time window.

        Args:
            num_comments: Number of comments to schedule
            window_seconds: Total available time window in seconds
            min_delay: Minimum delay between comments (seconds)
            max_delay: Maximum delay between comments (seconds)

        Returns:
            List of delay values in seconds
        """
        if num_comments <= 0:
            return []

        # Calculate average delay needed to fit all comments
        avg_needed = window_seconds / num_comments if num_comments > 0 else max_delay

        # Adjust min/max to fit the window
        effective_min = max(min_delay, 5)
        effective_max = min(max_delay, avg_needed * 2)

        if effective_min > effective_max:
            effective_min = effective_max * 0.5

        delays = []
        total = 0
        for _ in range(num_comments):
            delay = random.uniform(effective_min, effective_max)
            # Add human-like variance: occasionally longer pauses
            if random.random() < 0.1:
                delay *= random.uniform(1.5, 3.0)  # 10% chance of longer pause
            delays.append(delay)
            total += delay

        # Scale delays to fit within window if total exceeds window
        if total > window_seconds and total > 0:
            scale = window_seconds / total * 0.95  # 95% to leave some buffer
            delays = [d * scale for d in delays]

        random.shuffle(delays)
        return delays

    @staticmethod
    def time_until_window(start_hour: int, end_hour: int) -> tuple[float, float]:
        """
        Calculate seconds until the schedule window starts and the window duration.

        Returns:
            (seconds_until_start, window_duration_seconds)
        """
        now = datetime.now()
        window_start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        window_end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        if window_end <= window_start:
            window_end += timedelta(days=1)

        if now < window_start:
            wait = (window_start - now).total_seconds()
        elif now > window_end:
            # Window passed today, schedule for tomorrow
            window_start += timedelta(days=1)
            window_end += timedelta(days=1)
            wait = (window_start - now).total_seconds()
        else:
            wait = 0  # We're inside the window

        duration = (window_end - window_start).total_seconds()
        if wait == 0:
            duration = (window_end - now).total_seconds()

        return wait, max(duration, 0)

    def start_task(self, task_id: str, task_fn: Callable, *args, **kwargs):
        """
        Start a comment task in a new thread.
        If a concurrency limit is set, the task will wait for a free slot.

        Args:
            task_id: Unique identifier (e.g., 'reddit_user1')
            task_fn: The function to run (bot's main loop)
            *args, **kwargs: Arguments to pass to task_fn
        """
        with self._lock:
            if task_id in self._threads and self._threads[task_id].is_alive():
                logger.warning(f"Task {task_id} is already running")
                return False

            stop_event = threading.Event()
            self._stop_events[task_id] = stop_event

            semaphore = self._concurrency_semaphore

            def _wrapper():
                acquired = False
                try:
                    if semaphore:
                        self._status[task_id] = 'queued'
                        logger.info(f"Task {task_id} waiting for concurrency slot...")
                        # Wait for a slot, but check stop_event periodically
                        while not stop_event.is_set():
                            acquired = semaphore.acquire(timeout=2.0)
                            if acquired:
                                break
                        if stop_event.is_set():
                            self._status[task_id] = 'stopped'
                            return

                    self._status[task_id] = 'running'
                    logger.info(f"Task {task_id} is now running")
                    task_fn(stop_event, *args, **kwargs)
                    self._status[task_id] = 'stopped'
                except Exception as e:
                    logger.error(f"Task {task_id} failed: {e}", exc_info=True)
                    self._status[task_id] = 'error'
                finally:
                    if acquired and semaphore:
                        semaphore.release()
                        logger.debug(f"Task {task_id} released concurrency slot")

            thread = threading.Thread(target=_wrapper, name=f"bot-{task_id}", daemon=True)
            self._threads[task_id] = thread
            thread.start()
            logger.info(f"Started task: {task_id}")
            return True

    def stop_task(self, task_id: str, timeout: float = 30):
        """Stop a running task."""
        with self._lock:
            if task_id in self._stop_events:
                self._stop_events[task_id].set()
                logger.info(f"Stop signal sent to: {task_id}")

            if task_id in self._threads:
                thread = self._threads[task_id]
                if thread.is_alive():
                    thread.join(timeout=timeout)

        self._status[task_id] = 'stopped'

    def stop_all(self):
        """Stop all running tasks."""
        task_ids = list(self._stop_events.keys())
        for tid in task_ids:
            if tid in self._stop_events:
                self._stop_events[tid].set()
        logger.info(f"Stop signal sent to all {len(task_ids)} tasks")

        for tid in task_ids:
            if tid in self._threads and self._threads[tid].is_alive():
                self._threads[tid].join(timeout=10)

    def get_status(self, task_id: str) -> str:
        return self._status.get(task_id, 'unknown')

    def get_all_statuses(self) -> dict[str, str]:
        return dict(self._status)

    def is_running(self, task_id: str) -> bool:
        return (task_id in self._threads and
                self._threads[task_id].is_alive() and
                self._status.get(task_id) == 'running')

    def active_count(self) -> int:
        return sum(1 for s in self._status.values() if s == 'running')

    def cleanup(self):
        """Remove completed/stopped task entries."""
        with self._lock:
            dead = [tid for tid, t in self._threads.items() if not t.is_alive()]
            for tid in dead:
                del self._threads[tid]
                self._stop_events.pop(tid, None)
