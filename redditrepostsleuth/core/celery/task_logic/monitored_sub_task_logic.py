import logging
import time

from praw.exceptions import APIException, RedditAPIException
from prawcore import TooManyRequests

from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.exception import RateLimitException, NoIndexException, UtilApiException
from redditrepostsleuth.core.util.onlyfans_handling import check_user_for_only_fans
from redditrepostsleuth.submonitorsvc.monitored_sub_service import MonitoredSubService

log = logging.getLogger(__name__)

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
            check_user_for_only_fans(uow, post.author)
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

    total_check_time = round(time.perf_counter() - start, 5)

    if total_check_time > 20:
        log.warning('Long Check.  Time: %s | Subreddit: %s | Post ID: %s | Type: %s', total_check_time, monitored_sub.name, post.post_id, post.post_type)