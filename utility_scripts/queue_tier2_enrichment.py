#!/usr/bin/env python3
"""
Queue users for Tier 2 enrichment (Reddit API data).

This script finds users with spam scores but no Tier 2 data and queues them
for enrichment via Celery tasks. Tier 2 enrichment fetches account age,
karma, verified email status, profile links, etc. from the Reddit API.

Usage:
    # Queue 50 high-risk users (score >= 0.5) for enrichment
    python queue_tier2_enrichment.py --limit 50

    # Queue users with lower scores
    python queue_tier2_enrichment.py --min-score 0.3 --limit 100

    # Queue specific usernames
    python queue_tier2_enrichment.py --usernames user1 user2 user3

    # Dry run - show what would be queued without actually queuing
    python queue_tier2_enrichment.py --limit 50 --dry-run

    # Process synchronously (wait for results, useful for debugging)
    python queue_tier2_enrichment.py --limit 10 --sync

    # Include users where previous enrichment failed (retry failures)
    python queue_tier2_enrichment.py --limit 50 --include-failed

    # Re-enrich all users regardless of current status (refresh data)
    python queue_tier2_enrichment.py --limit 100 --force-all

    # Enrich and automatically re-score afterward
    python queue_tier2_enrichment.py --limit 50 --rescore-after
"""

import argparse
import sys
import time

# Add project root to path
sys.path.insert(0, '/home/barry/PycharmProjects/RedditRepostSleuth')

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


def get_unenriched_users(uowm, min_score: float, limit: int, include_failed: bool = False, force_all: bool = False) -> list:
    """
    Find users with spam scores but no Tier 2 enrichment.

    Args:
        uowm: Unit of work manager
        min_score: Minimum spam score to qualify
        limit: Maximum users to return
        include_failed: Whether to include users where enrichment previously failed
        force_all: If True, include all users regardless of current enrichment status

    Returns:
        List of (username, spam_score) tuples
    """
    from redditrepostsleuth.core.db.databasemodels import UserSpamFeatures

    with uowm.start() as uow:
        query = uow.session.query(
            UserSpamFeatures.username,
            UserSpamFeatures.spam_score
        ).filter(
            UserSpamFeatures.spam_score >= min_score,
        )

        if not force_all:
            query = query.filter(
                UserSpamFeatures.account_age_days.is_(None),  # No Tier 2 data yet
            )

        if not include_failed:
            query = query.filter(
                UserSpamFeatures.tier2_enrichment_failed.is_(False)
            )

        results = query.order_by(
            UserSpamFeatures.spam_score.desc()
        ).limit(limit).all()

        return [(r.username, r.spam_score) for r in results]


def get_users_needing_rescore(uowm, limit: int) -> list:
    """
    Find users who have Tier 2 data but haven't been re-scored yet.

    These are users where tier2_enriched_at is set but tier2_enhanced
    is not in their feature_data.

    Args:
        uowm: Unit of work manager
        limit: Maximum users to return

    Returns:
        List of (username, spam_score) tuples
    """
    from redditrepostsleuth.core.db.databasemodels import UserSpamFeatures

    with uowm.start() as uow:
        results = uow.session.query(
            UserSpamFeatures.username,
            UserSpamFeatures.spam_score
        ).filter(
            UserSpamFeatures.tier2_enriched_at.isnot(None),  # Has Tier 2 data
            UserSpamFeatures.account_age_days.isnot(None),   # Confirmed Tier 2
        ).order_by(
            UserSpamFeatures.spam_score.desc()
        ).limit(limit).all()

        # Filter to those without tier2_enhanced flag
        # (This check happens in Python since feature_data is JSON)
        users = []
        for r in results:
            spam_features = uow.spam_features.get_by_username(r.username)
            if spam_features and spam_features.feature_data:
                if not spam_features.feature_data.get('tier2_enhanced'):
                    users.append((r.username, r.spam_score))
            if len(users) >= limit:
                break

        return users


def queue_enrichment_async(usernames: list) -> dict:
    """
    Queue users for Tier 2 enrichment via Celery (async).

    Args:
        usernames: List of usernames to queue

    Returns:
        Dict with queued count
    """
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import enrich_user_features_tier2

    queued = 0
    for username in usernames:
        enrich_user_features_tier2.apply_async(
            args=[username],
            queue='spam_detection'
        )
        queued += 1

    return {'queued': queued}


def queue_rescore_async(usernames: list) -> dict:
    """
    Queue users for Tier 2 re-scoring via Celery (async).

    Args:
        usernames: List of usernames to queue

    Returns:
        Dict with queued count
    """
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import rescore_user_with_tier2

    queued = 0
    for username in usernames:
        rescore_user_with_tier2.apply_async(
            args=[username],
            queue='spam_detection'
        )
        queued += 1

    return {'queued': queued}


def process_enrichment_sync(usernames: list, delay: float = 1.5) -> dict:
    """
    Process users synchronously (blocking, for debugging).

    Args:
        usernames: List of usernames to process
        delay: Delay between users (rate limit protection)

    Returns:
        Dict with results summary
    """
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import enrich_user_features_tier2

    results = {
        'processed': 0,
        'enriched': 0,
        'suspended': 0,
        'skipped': 0,
        'failed': 0,
    }

    for i, username in enumerate(usernames):
        try:
            print(f"  [{i+1}/{len(usernames)}] Enriching {username}...", end=' ')

            # Call task directly (not via Celery)
            result = enrich_user_features_tier2(username)
            results['processed'] += 1

            if result:
                results['enriched'] += 1
                age = result.get('account_age_days', 'N/A')
                karma = result.get('total_karma', 'N/A')
                suspended = result.get('account_suspended', False)

                if suspended:
                    results['suspended'] += 1
                    print(f"SUSPENDED (age={age}d, karma={karma})")
                else:
                    print(f"OK (age={age}d, karma={karma})")
            else:
                results['skipped'] += 1
                print("SKIPPED (no data)")

            # Rate limit protection
            if i < len(usernames) - 1:
                time.sleep(delay)

        except Exception as e:
            results['failed'] += 1
            print(f"FAILED - {e}")

    return results


def process_rescore_sync(usernames: list) -> dict:
    """
    Process re-scoring synchronously (blocking, for debugging).

    Args:
        usernames: List of usernames to process

    Returns:
        Dict with results summary
    """
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import rescore_user_with_tier2

    results = {
        'processed': 0,
        'rescored': 0,
        'skipped': 0,
        'failed': 0,
        'high_risk': 0,
        'critical_risk': 0,
    }

    for i, username in enumerate(usernames):
        try:
            print(f"  [{i+1}/{len(usernames)}] Re-scoring {username}...", end=' ')

            result = rescore_user_with_tier2(username)
            results['processed'] += 1

            if result:
                results['rescored'] += 1
                score = result.get('score', 0)
                risk = result.get('risk_level', 'LOW')

                if risk == 'CRITICAL':
                    results['critical_risk'] += 1
                elif risk == 'HIGH':
                    results['high_risk'] += 1

                print(f"{risk} (score={score:.3f})")
            else:
                results['skipped'] += 1
                print("SKIPPED (insufficient data)")

        except Exception as e:
            results['failed'] += 1
            print(f"FAILED - {e}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Queue users for Tier 2 enrichment (Reddit API data)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--unenriched', action='store_true', default=True,
        help='Queue users needing Tier 2 enrichment (default)'
    )
    mode_group.add_argument(
        '--rescore-only', action='store_true',
        help='Only re-score users who already have Tier 2 data but were not re-scored'
    )
    mode_group.add_argument(
        '--usernames', nargs='+',
        help='Queue specific usernames for enrichment'
    )

    # Common options
    parser.add_argument(
        '--limit', '-n', type=int, default=50,
        help='Maximum number of users to queue (default: 50)'
    )
    parser.add_argument(
        '--min-score', type=float, default=0.5,
        help='Minimum spam score to qualify for enrichment (default: 0.5)'
    )
    parser.add_argument(
        '--include-failed', action='store_true',
        help='Include users where previous enrichment failed'
    )
    parser.add_argument(
        '--force-all', action='store_true',
        help='Include all users regardless of current enrichment status (re-enrich everyone)'
    )
    parser.add_argument(
        '--rescore-after', action='store_true',
        help='Automatically queue re-scoring after enrichment completes'
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
        '--delay', type=float, default=1.5,
        help='Delay between API calls in sync mode (default: 1.5s)'
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
    is_rescore = False

    if args.usernames:
        print(f"\nUsing provided usernames: {len(args.usernames)} users")
        users = [(u, 0.0) for u in args.usernames]

    elif args.rescore_only:
        print(f"\nFinding users with Tier 2 data needing re-scoring...")
        users = get_users_needing_rescore(uowm, args.limit)
        print(f"Found {len(users)} users needing re-scoring")
        is_rescore = True

    else:  # Default: unenriched
        include_failed_str = " (including failed)" if args.include_failed else ""
        force_all_str = " [FORCE ALL]" if args.force_all else ""
        print(f"\nFinding users (score >= {args.min_score}){include_failed_str}{force_all_str}...")
        users = get_unenriched_users(uowm, args.min_score, args.limit, args.include_failed, args.force_all)
        if args.force_all:
            print(f"Found {len(users)} users for Tier 2 enrichment (including already enriched)")
        else:
            print(f"Found {len(users)} users needing Tier 2 enrichment")

    if not users:
        print("No users to process.")
        return

    # Show preview
    action = "re-score" if is_rescore else "enrich"
    rescore_suffix = " (+ re-score)" if args.rescore_after and not is_rescore else ""
    print(f"\nUsers to {action}{rescore_suffix} ({len(users)}):")
    for i, (username, score) in enumerate(users[:10]):
        print(f"  {i+1}. {username} (score: {score:.3f})")

    if len(users) > 10:
        print(f"  ... and {len(users) - 10} more")

    # Extract just usernames
    usernames = [u[0] for u in users]

    if args.dry_run:
        print(f"\n[DRY RUN] Would queue {len(usernames)} users for {action}")
        if args.rescore_after and not is_rescore:
            print(f"[DRY RUN] Would also queue {len(usernames)} users for re-scoring after enrichment")
        return

    # Queue or process users
    if is_rescore:
        if args.sync:
            print(f"\nRe-scoring {len(usernames)} users synchronously...")
            results = process_rescore_sync(usernames)
            print(f"\nResults:")
            print(f"  Processed: {results['processed']}")
            print(f"  Re-scored: {results['rescored']}")
            print(f"  Skipped: {results['skipped']}")
            print(f"  Failed: {results['failed']}")
            print(f"  High Risk: {results['high_risk']}")
            print(f"  Critical Risk: {results['critical_risk']}")
        else:
            print(f"\nQueuing {len(usernames)} users for async re-scoring...")
            results = queue_rescore_async(usernames)
            print(f"Queued {results['queued']} users to spam_detection_temp queue")
    else:
        if args.sync:
            print(f"\nEnriching {len(usernames)} users synchronously (delay={args.delay}s)...")
            print("Note: This makes Reddit API calls. Be patient.\n")
            results = process_enrichment_sync(usernames, args.delay)
            print(f"\nEnrichment Results:")
            print(f"  Processed: {results['processed']}")
            print(f"  Enriched: {results['enriched']}")
            print(f"  Suspended: {results['suspended']}")
            print(f"  Skipped: {results['skipped']}")
            print(f"  Failed: {results['failed']}")

            if args.rescore_after:
                print(f"\nRe-scoring {len(usernames)} users synchronously...")
                rescore_results = process_rescore_sync(usernames)
                print(f"\nRe-scoring Results:")
                print(f"  Processed: {rescore_results['processed']}")
                print(f"  Re-scored: {rescore_results['rescored']}")
                print(f"  Skipped: {rescore_results['skipped']}")
                print(f"  Failed: {rescore_results['failed']}")
                print(f"  High Risk: {rescore_results['high_risk']}")
                print(f"  Critical Risk: {rescore_results['critical_risk']}")
        else:
            print(f"\nQueuing {len(usernames)} users for async enrichment...")
            results = queue_enrichment_async(usernames)
            print(f"Queued {results['queued']} users to spam_detection_temp queue")

            if args.rescore_after:
                print(f"\nQueuing {len(usernames)} users for async re-scoring...")
                rescore_results = queue_rescore_async(usernames)
                print(f"Queued {rescore_results['queued']} users for re-scoring to spam_detection_temp queue")

            print("Monitor progress with: celery -A redditrepostsleuth.core.celery inspect active")


if __name__ == '__main__':
    main()
