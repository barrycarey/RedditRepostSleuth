#!/usr/bin/env python3
"""
Queue users for spam scoring/feature extraction.

This script finds users with enough activity data and queues them
for spam detection processing via Celery tasks.

Usage:
    # Queue 100 unscored users with at least 10 posts
    python queue_spam_scoring.py --limit 100 --min-posts 10

    # Queue top reposters from last 30 days
    python queue_spam_scoring.py --top-reposters --days 30 --limit 50

    # Re-score users whose scores are older than 7 days
    python queue_spam_scoring.py --rescore-stale --stale-days 7 --limit 100

    # Dry run - show what would be queued without actually queuing
    python queue_spam_scoring.py --limit 100 --dry-run

    # Process synchronously (wait for results, useful for debugging)
    python queue_spam_scoring.py --limit 10 --sync
"""

import argparse
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, '/home/barry/PycharmProjects/RedditRepostSleuth')

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


def get_unscored_users(uowm, min_posts: int, limit: int) -> list:
    """
    Find users with enough activity but no spam score.

    Uses LEFT JOIN exclusion pattern for efficient query execution.

    Args:
        uowm: Unit of work manager
        min_posts: Minimum posts required for analysis
        limit: Maximum users to return

    Returns:
        List of usernames
    """
    from sqlalchemy import func, and_
    from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking, UserSpamFeatures

    with uowm.start() as uow:
        # LEFT JOIN exclusion pattern - much faster than NOT IN subquery
        results = uow.session.query(
            AuthorActivityTracking.author,
            func.count(AuthorActivityTracking.id).label('post_count')
        ).outerjoin(
            UserSpamFeatures,
            and_(
                AuthorActivityTracking.author == UserSpamFeatures.username,
                UserSpamFeatures.spam_score.isnot(None)
            )
        ).filter(
            UserSpamFeatures.username.is_(None),  # LEFT JOIN exclusion
            AuthorActivityTracking.author != '[deleted]',
            AuthorActivityTracking.author.isnot(None)
        ).group_by(
            AuthorActivityTracking.author
        ).having(
            func.count(AuthorActivityTracking.id) >= min_posts
        ).order_by(
            func.count(AuthorActivityTracking.id).desc()
        ).limit(limit).all()

        return [(r.author, r.post_count) for r in results]


def get_stale_scored_users(uowm, stale_days: int, limit: int) -> list:
    """
    Find users with stale (old) spam scores that need re-scoring.

    Args:
        uowm: Unit of work manager
        stale_days: Consider scores older than this many days as stale
        limit: Maximum users to return

    Returns:
        List of (username, post_count, last_scored) tuples
    """
    from sqlalchemy import func
    from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking, UserSpamFeatures

    cutoff = datetime.utcnow() - timedelta(days=stale_days)

    with uowm.start() as uow:
        results = uow.session.query(
            UserSpamFeatures.username,
            UserSpamFeatures.total_posts,
            UserSpamFeatures.computed_at
        ).filter(
            UserSpamFeatures.computed_at < cutoff
        ).order_by(
            UserSpamFeatures.computed_at.asc()
        ).limit(limit).all()

        return [(r.username, r.total_posts, r.computed_at) for r in results]


def get_top_reposters(uowm, days: int, min_reposts: int, limit: int) -> list:
    """
    Find top reposters that need scoring.

    Uses LEFT JOIN exclusion pattern for efficient query execution.

    Args:
        uowm: Unit of work manager
        days: Look back period
        min_reposts: Minimum reposts to qualify
        limit: Maximum users to return

    Returns:
        List of (username, repost_count) tuples
    """
    from sqlalchemy import func, and_
    from redditrepostsleuth.core.db.databasemodels import Repost, UserSpamFeatures

    cutoff = datetime.utcnow() - timedelta(days=days)

    with uowm.start() as uow:
        # LEFT JOIN exclusion pattern - much faster than NOT IN subquery
        results = uow.session.query(
            Repost.author,
            func.count(Repost.id).label('repost_count')
        ).outerjoin(
            UserSpamFeatures,
            and_(
                Repost.author == UserSpamFeatures.username,
                UserSpamFeatures.spam_score.isnot(None),
                UserSpamFeatures.computed_at >= cutoff
            )
        ).filter(
            Repost.detected_at >= cutoff,
            Repost.author.isnot(None),
            Repost.author != '[deleted]',
            UserSpamFeatures.username.is_(None)  # LEFT JOIN exclusion
        ).group_by(
            Repost.author
        ).having(
            func.count(Repost.id) >= min_reposts
        ).order_by(
            func.count(Repost.id).desc()
        ).limit(limit).all()

        return [(r.author, r.repost_count) for r in results]


def get_high_activity_users(uowm, min_posts: int, days: int, limit: int) -> list:
    """
    Find users with high recent activity.

    Uses LEFT JOIN exclusion pattern for efficient query execution.

    Args:
        uowm: Unit of work manager
        min_posts: Minimum posts in period
        days: Look back period
        limit: Maximum users to return

    Returns:
        List of (username, post_count) tuples
    """
    from sqlalchemy import func, and_
    from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking, UserSpamFeatures

    cutoff = datetime.utcnow() - timedelta(days=days)

    with uowm.start() as uow:
        # LEFT JOIN exclusion pattern - much faster than NOT IN subquery
        results = uow.session.query(
            AuthorActivityTracking.author,
            func.count(AuthorActivityTracking.id).label('post_count')
        ).outerjoin(
            UserSpamFeatures,
            and_(
                AuthorActivityTracking.author == UserSpamFeatures.username,
                UserSpamFeatures.spam_score.isnot(None)
            )
        ).filter(
            AuthorActivityTracking.created_at >= cutoff,
            UserSpamFeatures.username.is_(None),  # LEFT JOIN exclusion
            AuthorActivityTracking.author != '[deleted]',
            AuthorActivityTracking.author.isnot(None)
        ).group_by(
            AuthorActivityTracking.author
        ).having(
            func.count(AuthorActivityTracking.id) >= min_posts
        ).order_by(
            func.count(AuthorActivityTracking.id).desc()
        ).limit(limit).all()

        return [(r.author, r.post_count) for r in results]


def queue_users_async(usernames: list, update_user_review: bool = True) -> dict:
    """
    Queue users for scoring via Celery (async).

    Args:
        usernames: List of usernames to queue
        update_user_review: Whether to update user_review table

    Returns:
        Dict with queued count
    """
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import score_and_flag_user

    queued = 0
    for username in usernames:
        score_and_flag_user.apply_async(
            args=[username, update_user_review],
            queue='spam_detection'
        )
        queued += 1

    return {'queued': queued}


def queue_users_sync(usernames: list, update_user_review: bool = True) -> dict:
    """
    Process users synchronously (blocking, for debugging).

    Args:
        usernames: List of usernames to process
        update_user_review: Whether to update user_review table

    Returns:
        Dict with results summary
    """
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import score_and_flag_user

    results = {
        'processed': 0,
        'scored': 0,
        'skipped': 0,
        'failed': 0,
        'high_risk': 0,
        'critical_risk': 0,
    }

    for username in usernames:
        try:
            # Call task directly (not via Celery)
            result = score_and_flag_user(username, update_user_review)
            results['processed'] += 1

            if result:
                results['scored'] += 1
                risk = result.get('risk_level', 'LOW')
                if risk == 'CRITICAL':
                    results['critical_risk'] += 1
                    print(f"  CRITICAL: {username} - score: {result['score']:.2f}")
                elif risk == 'HIGH':
                    results['high_risk'] += 1
                    print(f"  HIGH: {username} - score: {result['score']:.2f}")
                else:
                    print(f"  {risk}: {username} - score: {result['score']:.2f}")
            else:
                results['skipped'] += 1
                print(f"  SKIPPED: {username} (insufficient data)")

        except Exception as e:
            results['failed'] += 1
            print(f"  FAILED: {username} - {e}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Queue users for spam scoring/feature extraction',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--unscored', action='store_true', default=True,
        help='Queue unscored users with enough posts (default)'
    )
    mode_group.add_argument(
        '--top-reposters', action='store_true',
        help='Queue top reposters'
    )
    mode_group.add_argument(
        '--rescore-stale', action='store_true',
        help='Re-score users with old scores'
    )
    mode_group.add_argument(
        '--high-activity', action='store_true',
        help='Queue users with high recent activity'
    )
    mode_group.add_argument(
        '--usernames', nargs='+',
        help='Queue specific usernames'
    )

    # Common options
    parser.add_argument(
        '--limit', '-n', type=int, default=100,
        help='Maximum number of users to queue (default: 100)'
    )
    parser.add_argument(
        '--min-posts', type=int, default=10,
        help='Minimum posts required for analysis (default: 10)'
    )
    parser.add_argument(
        '--days', type=int, default=30,
        help='Look back period in days (default: 30)'
    )
    parser.add_argument(
        '--min-reposts', type=int, default=5,
        help='Minimum reposts for --top-reposters (default: 5)'
    )
    parser.add_argument(
        '--stale-days', type=int, default=7,
        help='Days before score is considered stale (default: 7)'
    )

    # Execution options
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be queued without actually queuing'
    )
    parser.add_argument(
        '--sync', action='store_true',
        help='Process synchronously (blocking, useful for debugging)'
    )
    parser.add_argument(
        '--no-user-review', action='store_true',
        help='Do not update user_review table'
    )
    parser.add_argument(
        '--config', type=str,
        default='/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config_dev.json',
        help='Path to config file'
    )

    args = parser.parse_args()

    # Initialize database connection
    print(f"Loading config from: {args.config}")
    config = Config(args.config)
    uowm = UnitOfWorkManager(get_db_engine(config))

    # Determine which users to queue
    users = []

    if args.usernames:
        print(f"\nUsing provided usernames: {len(args.usernames)} users")
        users = [(u, 0) for u in args.usernames]

    elif args.top_reposters:
        print(f"\nFinding top reposters (last {args.days} days, min {args.min_reposts} reposts)...")
        users = get_top_reposters(uowm, args.days, args.min_reposts, args.limit)
        print(f"Found {len(users)} top reposters needing scoring")

    elif args.rescore_stale:
        print(f"\nFinding users with stale scores (>{args.stale_days} days old)...")
        users = get_stale_scored_users(uowm, args.stale_days, args.limit)
        print(f"Found {len(users)} users with stale scores")

    elif args.high_activity:
        print(f"\nFinding high activity users (last {args.days} days, min {args.min_posts} posts)...")
        users = get_high_activity_users(uowm, args.min_posts, args.days, args.limit)
        print(f"Found {len(users)} high activity users")

    else:  # Default: unscored
        print(f"\nFinding unscored users (min {args.min_posts} posts)...")
        users = get_unscored_users(uowm, args.min_posts, args.limit)
        print(f"Found {len(users)} unscored users")

    if not users:
        print("No users to process.")
        return

    # Show preview
    print(f"\nUsers to process ({len(users)}):")
    for i, user_data in enumerate(users[:10]):
        if len(user_data) == 3:  # stale scores include timestamp
            username, count, timestamp = user_data
            print(f"  {i+1}. {username} ({count} posts, last scored: {timestamp})")
        else:
            username, count = user_data
            print(f"  {i+1}. {username} ({count} posts/reposts)")

    if len(users) > 10:
        print(f"  ... and {len(users) - 10} more")

    # Extract just usernames
    usernames = [u[0] for u in users]

    if args.dry_run:
        print(f"\n[DRY RUN] Would queue {len(usernames)} users for scoring")
        return

    # Queue or process users
    update_review = not args.no_user_review

    if args.sync:
        print(f"\nProcessing {len(usernames)} users synchronously...")
        results = queue_users_sync(usernames, update_review)
        print(f"\nResults:")
        print(f"  Processed: {results['processed']}")
        print(f"  Scored: {results['scored']}")
        print(f"  Skipped: {results['skipped']}")
        print(f"  Failed: {results['failed']}")
        print(f"  High Risk: {results['high_risk']}")
        print(f"  Critical Risk: {results['critical_risk']}")
    else:
        print(f"\nQueuing {len(usernames)} users for async processing...")
        results = queue_users_async(usernames, update_review)
        print(f"Queued {results['queued']} users to spam_detection queue")
        print("Monitor progress with: celery -A redditrepostsleuth.core.celery inspect active")


if __name__ == '__main__':
    main()
