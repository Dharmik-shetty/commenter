"""
Comment distribution algorithm.
Ensures comments are spread evenly across subreddits/keywords rather than
concentrating on a few sources.
"""

import math
import random
import logging

logger = logging.getLogger(__name__)


def distribute_comments(source_posts: dict[str, list[dict]], total_limit: int) -> dict[str, list[dict]]:
    """
    Distribute a total comment budget evenly across sources (subreddits or keywords).

    The algorithm:
    1. Calculate a fair base share per source (total_limit / num_sources)
    2. First pass: allocate min(fair_share, available_posts) to each source
    3. Second pass: redistribute remaining budget to sources with extra posts
    4. Shuffle allocated posts within each source for variety

    Args:
        source_posts: {source_name: [list of eligible post dicts]}
        total_limit: Maximum total comments across all sources

    Returns:
        {source_name: [allocated posts to comment on]}
    """
    if not source_posts:
        return {}

    n_sources = len(source_posts)
    if total_limit <= 0:
        return {src: [] for src in source_posts}

    base_share = total_limit // n_sources
    remainder = total_limit % n_sources

    allocation = {}
    remaining_budget = 0

    # Shuffle source order to avoid bias toward first sources
    source_names = list(source_posts.keys())
    random.shuffle(source_names)

    # --- First pass: allocate base share ---
    for i, src in enumerate(source_names):
        posts = source_posts[src]
        share = base_share + (1 if i < remainder else 0)

        if len(posts) >= share:
            # Have enough posts, allocate fair share
            selected = random.sample(posts, share)
            allocation[src] = selected
        else:
            # Fewer posts than share, take all and note the surplus
            allocation[src] = list(posts)
            remaining_budget += share - len(posts)

    # --- Second pass: redistribute surplus budget ---
    if remaining_budget > 0:
        # Sort sources by available extra posts (most extra first)
        sources_with_extra = []
        for src in source_names:
            current = len(allocation[src])
            available = len(source_posts[src]) - current
            if available > 0:
                sources_with_extra.append((src, available))

        sources_with_extra.sort(key=lambda x: x[1], reverse=True)

        # Distribute remaining budget evenly among sources with extra capacity
        while remaining_budget > 0 and sources_with_extra:
            per_source_extra = max(1, remaining_budget // len(sources_with_extra))
            next_round = []

            for src, available in sources_with_extra:
                if remaining_budget <= 0:
                    break
                give = min(per_source_extra, available, remaining_budget)
                if give > 0:
                    current = len(allocation[src])
                    extra_posts = source_posts[src][current:current + give]
                    allocation[src].extend(extra_posts)
                    remaining_budget -= give
                    new_available = available - give
                    if new_available > 0:
                        next_round.append((src, new_available))

            sources_with_extra = next_round

    # Log distribution summary
    total_allocated = sum(len(v) for v in allocation.values())
    dist_summary = {src: len(posts) for src, posts in allocation.items()}
    logger.info(f"Distribution: {total_allocated}/{total_limit} comments across "
                f"{n_sources} sources: {dist_summary}")

    return allocation


def distribute_across_accounts(accounts: list[dict], source_allocation: dict[str, list[dict]]) -> dict[str, dict[str, list[dict]]]:
    """
    Further distribute allocated posts across multiple accounts.

    Args:
        accounts: List of account dicts with 'username' and 'daily_limit'
        source_allocation: Output from distribute_comments()

    Returns:
        {account_username: {source_name: [posts to comment on]}}
    """
    if not accounts or not source_allocation:
        return {}

    # Flatten all allocated posts with their source
    all_tasks = []
    for src, posts in source_allocation.items():
        for post in posts:
            all_tasks.append((src, post))

    random.shuffle(all_tasks)

    # Distribute tasks across accounts respecting daily limits
    account_tasks = {acc['username']: {} for acc in accounts}
    account_remaining = {acc['username']: acc.get('daily_limit', 1000) - acc.get('comments_today', 0)
                         for acc in accounts}

    task_idx = 0
    while task_idx < len(all_tasks):
        # Round-robin across accounts
        assigned = False
        for acc in accounts:
            if task_idx >= len(all_tasks):
                break
            uname = acc['username']
            if account_remaining[uname] > 0:
                src, post = all_tasks[task_idx]
                if src not in account_tasks[uname]:
                    account_tasks[uname][src] = []
                account_tasks[uname][src].append(post)
                account_remaining[uname] -= 1
                task_idx += 1
                assigned = True

        if not assigned:
            break  # All accounts at their limits

    summary = {u: sum(len(p) for p in srcs.values()) for u, srcs in account_tasks.items()}
    logger.info(f"Account distribution: {summary}")

    return account_tasks
