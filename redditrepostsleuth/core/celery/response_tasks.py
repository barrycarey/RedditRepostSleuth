import json
import time
from random import randint

import requests
from celery import Task
from praw.exceptions import RedditAPIException, APIException
from prawcore import TooManyRequests
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import LoadSubredditException, NoIndexException, RateLimitException
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import update_log_context_data
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor

log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post_ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[ContextFilter()]
)


class SubMonitorTask(Task):

    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.reddit_manager = RedditManager(self.reddit)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        event_logger = EventLogging(config=self.config)
        response_handler = ResponseHandler(self.reddit, self.uowm, event_logger, source='submonitor', live_response=self.config.live_responses)
        dup_image_svc = DuplicateImageService(self.uowm, event_logger, self.reddit, config=self.config)
        response_builder = ResponseBuilder(self.uowm)
        self.sub_monitor = SubMonitor(dup_image_svc, self.uowm, self.reddit, response_builder, response_handler, event_logger=event_logger, config=self.config)
        self.blacklisted_posts = []


@celery.task(
    bind=True,
    base=SubMonitorTask,
    serializer='pickle',
    autoretry_for=(TooManyRequests, RedditAPIException, NoIndexException, RateLimitException),
    retry_kwards={'max_retries': 3}
)
def sub_monitor_check_post(self, post_id: str, monitored_sub: MonitoredSub):
    update_log_context_data(log, {'trace_id': str(randint(100000, 999999)), 'post_id': post_id,
                                  'subreddit': monitored_sub.name, 'service': 'Subreddit_Monitor'})
    if self.sub_monitor.has_post_been_checked(post_id):
        log.debug('Post %s has already been checked', post_id)
        return
    if post_id in self.blacklisted_posts:
        log.debug('Skipping blacklisted post')
        return

    start = time.perf_counter()
    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(post_id)
        if not post:
            log.info('Post %s does exist', post_id)
            return
        if not post.post_type:
            log.warning('Unknown post type for %s - https://redd.it/%s', post.post_id, post.post_id)
            return

        self.sub_monitor.handle_only_fans_check(post, uow, monitored_sub)
        self.sub_monitor.handle_high_volume_reposter_check(post, uow, monitored_sub)

    title_keywords = []
    if monitored_sub.title_ignore_keywords:
        title_keywords = monitored_sub.title_ignore_keywords.split(',')

    if not self.sub_monitor.should_check_post(
            post,
            monitored_sub,
            title_keyword_filter=title_keywords
    ):
        return

    try:
        results = self.sub_monitor.check_submission(monitored_sub, post)
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
        self.sub_monitor.create_checked_post(results, monitored_sub)

    total_check_time = round(time.perf_counter() - start, 5)

    if total_check_time > 20:
        log.warning('Long Check.  Time: %s | Subreddit: %s | Post ID: %s | Type: %s', total_check_time, monitored_sub.name, post.post_id, post.post_type)

    if len(self.blacklisted_posts) > 10000:
        log.info('Resetting blacklisted posts')
        self.blacklisted_posts = []


@celery.task(bind=True, base=SubMonitorTask, serializer='pickle', ignore_results=True, autoretry_for=(LoadSubredditException,), retry_kwards={'max_retries': 3})
def process_monitored_sub(self, monitored_sub):

    submission_ids_to_check = []

    if monitored_sub.is_private:
        # Don't run through proxy if it's private
        log.info('Loading all submissions from %s (PRIVATE)', monitored_sub.name)
        submission_ids_to_check += [sub.id for sub in self.reddit.subreddit(monitored_sub.name).new(limit=500)]
    else:
        try:
            log.info('Loading all submissions from %s', monitored_sub.name)
            r = requests.get(f'{self.config.util_api}/reddit/subreddit', params={'subreddit': monitored_sub.name, 'limit': 500})
        except ConnectionError:
            log.error('Connection error with util API')
            return
        except Exception as e:
            log.error('Error getting new posts from util api', exc_info=True)
            return

        if r.status_code == 403:
            log.error('Monitored sub %s is private.  Skipping', monitored_sub.name)
            return

        if r.status_code != 200:
            log.error('Bad status code from Util API %s for %s', r.status_code, monitored_sub.name)
            return

        response_data = json.loads(r.text)

        submission_ids_to_check += [submission['id'] for submission in response_data]

    for submission_id in submission_ids_to_check:
        sub_monitor_check_post.apply_async((submission_id, monitored_sub), queue='submonitor_private')

    log.info('All submissions from %s sent to queue', monitored_sub.name)

