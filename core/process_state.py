"""
Persistent process state storage for resumable bot runs.

Stores per-task progress in a JSON file with atomic writes so a crash/restart
can continue from the latest checkpoint.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ProcessStateStore:
    """Thread-safe JSON state store with atomic write semantics."""

    SCHEMA_VERSION = 1

    def __init__(self, state_file: str = 'data/process_state.json', max_urls_per_task: int = 5000):
        self._state_file = state_file
        self._max_urls_per_task = max_urls_per_task
        self._lock = threading.RLock()
        self._state = {
            'version': self.SCHEMA_VERSION,
            'updated_at': None,
            'tasks': {},
        }
        self._ensure_parent_dir()
        self._load()

    def _ensure_parent_dir(self):
        parent = os.path.dirname(self._state_file)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _load(self):
        with self._lock:
            if not os.path.exists(self._state_file):
                return

            try:
                with open(self._state_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)

                if not isinstance(loaded, dict):
                    logger.warning('State file invalid root type. Starting with empty state.')
                    return

                tasks = loaded.get('tasks', {})
                if not isinstance(tasks, dict):
                    tasks = {}

                self._state = {
                    'version': int(loaded.get('version', self.SCHEMA_VERSION)),
                    'updated_at': loaded.get('updated_at'),
                    'tasks': tasks,
                }
                logger.info(f"Loaded process state for {len(tasks)} task(s)")
            except Exception as e:
                logger.error(f"Failed loading process state file: {e}", exc_info=True)

    def _save(self):
        with self._lock:
            self._state['updated_at'] = datetime.utcnow().isoformat()
            tmp_path = f"{self._state_file}.tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, ensure_ascii=True, indent=2)
            os.replace(tmp_path, self._state_file)

    @staticmethod
    def _today_key() -> str:
        return datetime.utcnow().date().isoformat()

    def get_resume_state(self, task_id: str) -> dict[str, Any]:
        """Return resume payload for a task, scoped to today's run only."""
        with self._lock:
            task = self._state.get('tasks', {}).get(task_id, {})
            if task.get('run_date') != self._today_key():
                return {}
            return {
                'current_round': int(task.get('current_round', 0) or 0),
                'commented_urls': list(task.get('commented_urls', [])),
            }

    def mark_started(self, task_id: str, platform: str, username: str):
        with self._lock:
            now = datetime.utcnow().isoformat()
            task = self._state['tasks'].get(task_id, {})
            run_date = self._today_key()

            # Fresh run for a new day: keep metadata, reset checkpoints.
            if task.get('run_date') != run_date:
                task['commented_urls'] = []
                task['current_round'] = 0

            task.update({
                'task_id': task_id,
                'platform': platform,
                'username': username,
                'status': 'running',
                'run_date': run_date,
                'started_at': task.get('started_at') or now,
                'last_checkpoint_at': now,
                'last_error': '',
            })
            self._state['tasks'][task_id] = task
            self._save()

    def checkpoint(self, task_id: str, *, processed_url: str | None = None,
                   current_round: int | None = None):
        with self._lock:
            task = self._state['tasks'].get(task_id)
            if not task:
                return

            if current_round is not None:
                task['current_round'] = int(current_round)

            if processed_url:
                existing = task.get('commented_urls', [])
                # Preserve insertion order while deduplicating.
                if processed_url not in existing:
                    existing.append(processed_url)
                    if len(existing) > self._max_urls_per_task:
                        existing = existing[-self._max_urls_per_task:]
                    task['commented_urls'] = existing

            task['last_checkpoint_at'] = datetime.utcnow().isoformat()
            self._save()

    def mark_stopped(self, task_id: str, reason: str = 'stopped'):
        with self._lock:
            task = self._state['tasks'].get(task_id)
            if not task:
                return
            task['status'] = 'stopped'
            task['ended_at'] = datetime.utcnow().isoformat()
            task['last_error'] = reason
            self._save()

    def mark_completed(self, task_id: str):
        with self._lock:
            task = self._state['tasks'].get(task_id)
            if not task:
                return
            task['status'] = 'completed'
            task['ended_at'] = datetime.utcnow().isoformat()
            task['last_error'] = ''
            self._save()

    def mark_error(self, task_id: str, error_message: str):
        with self._lock:
            task = self._state['tasks'].get(task_id)
            if not task:
                return
            task['status'] = 'error'
            task['ended_at'] = datetime.utcnow().isoformat()
            task['last_error'] = (error_message or '')[:1000]
            self._save()

    def clear(self):
        with self._lock:
            self._state = {
                'version': self.SCHEMA_VERSION,
                'updated_at': datetime.utcnow().isoformat(),
                'tasks': {},
            }
            self._save()

    def summary(self) -> dict[str, Any]:
        with self._lock:
            tasks = self._state.get('tasks', {})
            resumable = 0
            for t in tasks.values():
                if t.get('run_date') == self._today_key() and t.get('commented_urls'):
                    resumable += 1

            return {
                'task_count': len(tasks),
                'resumable_today': resumable,
                'updated_at': self._state.get('updated_at'),
            }

    def get_crash_resumable_tasks(self) -> list[dict[str, Any]]:
        """
        Return tasks that should be auto-resumed after a server crash/restart.

        Criteria:
        - Same UTC run day
        - Last known status was running (likely interrupted unexpectedly)
        """
        with self._lock:
            today = self._today_key()
            results = []
            for task_id, task in self._state.get('tasks', {}).items():
                if task.get('run_date') != today:
                    continue
                if task.get('status') != 'running':
                    continue
                results.append({
                    'task_id': task_id,
                    'platform': task.get('platform', ''),
                    'username': task.get('username', ''),
                })
            return results
