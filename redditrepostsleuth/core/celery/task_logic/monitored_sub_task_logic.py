import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from praw.exceptions import APIException, RedditAPIException
from prawcore import TooManyRequests

from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub as MonitoredSubModel
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.exception import RateLimitException, NoIndexException, UtilApiException
from redditrepostsleuth.core.services.spam.spam_config_helper import get_spam_config, SpamDetectionConfig
from redditrepostsleuth.core.util.onlyfans_handling import check_user_for_only_fans
from redditrepostsleuth.submonitorsvc.monitored_sub_service import MonitoredSubService

log = logging.getLogger(__name__)

# Minimum posts required before spam analysis
MIN_POSTS_FOR_SPAM_ANALYSIS = 5
# Don't re-analyze users within this window
SPAM_ANALYSIS_COOLDOWN_DAYS = 7

def process_monitored_subreddit_submission(post_id: str, monitored_sub_svc: MonitoredSubService, uow: UnitOfWork) -> None:

    start = time.perf_counter()

    post = uow.posts.get_by_post_id(post_id)

    if not post:
        log.warning('Post %s does exist', post_id)
        return

    if not post.post_type:
        log.warning('Unknown post type for %s - https://redd.it/%s', post.post_id, post.post_id)
        return

    monitored_sub = uow.monitored_sub.get_by_sub(post.subreddit)

    if monitored_sub.adult_promoter_remove_post or monitored_sub.adult_promoter_ban_user or monitored_sub.adult_promoter_notify_mod_mail:
        try:
            check_user_for_only_fans(uow, post.author, monitored_sub_svc.reddit)
        except (UtilApiException, ConnectionError, TooManyRequests) as e:
            log.warning('Failed to do onlyfans check for user %s', post.author)

    whitelisted_user = uow.user_whitelist.get_by_username_and_subreddit(post.author, monitored_sub.id)

    monitored_sub_svc.handle_only_fans_check(post, uow, monitored_sub, whitelisted_user=whitelisted_user)
    monitored_sub_svc.handle_high_volume_reposter_check(post, uow, monitored_sub, whitelisted_user=whitelisted_user)

    title_keywords = []
    if monitored_sub.title_ignore_keywords:
        title_keywords = monitored_sub.title_ignore_keywords.split(',')

    if not monitored_sub_svc.should_check_post(
            post,
            monitored_sub,
            title_keyword_filter=title_keywords,
            whitelisted_user=whitelisted_user
    ):
        return

    try:
        results = monitored_sub_svc.check_submission(monitored_sub, post)
    except (TooManyRequests, RateLimitException):
        log.warning('Currently out of API credits')
        raise
    except NoIndexException:
        log.warning('No indexes available to do post check')
        raise
    except APIException:
        log.exception('Unexpected Reddit API error')
        raise
    except RedditAPIException:
        log.exception('')
        raise
    except Exception as e:
        log.exception('')
        return

    if results:
        monitored_sub_svc.create_checked_post(results, monitored_sub)

    # Queue spam analysis for the post author (non-blocking)
    _check_author_for_spam(post, monitored_sub, uow)

    total_check_time = round(time.perf_counter() - start, 5)

    if total_check_time > 20:
        log.warning('Long Check.  Time: %s | Subreddit: %s | Post ID: %s | Type: %s', total_check_time, monitored_sub.name, post.post_id, post.post_type)


def _should_analyze_user(username: str, uow: UnitOfWork) -> bool:
    """
    Determine if a user should be analyzed for spam.

    Checks:
    - User is not None or [deleted]
    - User is not whitelisted
    - User has not been recently analyzed
    - User has minimum number of posts

    Args:
        username: The Reddit username to check
        uow: UnitOfWork for database access

    Returns:
        True if the user should be analyzed
    """
    if not username or username == '[deleted]':
        log.debug('Skipping spam analysis for invalid username: %s', username)
        return False

    # Check if recently analyzed
    if uow.spam_features.user_was_recently_analyzed(username, within_days=SPAM_ANALYSIS_COOLDOWN_DAYS):
        log.debug('User %s was recently analyzed for spam, skipping', username)
        return False

    # Check minimum post count via author activity
    activity_count = uow.author_activity.count_by_author(username)
    if activity_count < MIN_POSTS_FOR_SPAM_ANALYSIS:
        log.debug('User %s has %d posts, below minimum %d for spam analysis',
                  username, activity_count, MIN_POSTS_FOR_SPAM_ANALYSIS)
        return False

    return True


def _check_author_for_spam(
    post: Post,
    monitored_sub: MonitoredSubModel,
    uow: UnitOfWork
) -> None:
    """
    Queue spam analysis for the post author if appropriate.

    This function does NOT block the main flow - it queues
    an async task for spam scoring.

    Args:
        post: The Post being checked
        monitored_sub: The MonitoredSub configuration
        uow: UnitOfWork for database access
    """
    spam_config = get_spam_config(monitored_sub)

    if not spam_config.enabled:
        log.debug('Spam detection not enabled for r/%s', monitored_sub.name)
        return

    if not _should_analyze_user(post.author, uow):
        return

    # Queue async spam scoring task
    try:
        from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import score_and_flag_user
        score_and_flag_user.delay(post.author, update_user_review=True)
        log.debug('Queued spam analysis for user %s (post %s in r/%s)',
                  post.author, post.post_id, monitored_sub.name)
    except Exception as e:
        # Don't let spam analysis failures affect the main flow
        log.warning('Failed to queue spam analysis for %s: %s', post.author, str(e))