import json
import time
from datetime import datetime
from random import randint
from typing import Text

import requests
from celery import Task
from praw.exceptions import APIException
from prawcore import ResponseException
from redlock import RedLockError
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, Summons
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import LoadSubredditException
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.model.events.summonsevent import SummonsEvent
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import get_redlock_factory, update_log_context_data
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.ingestsvc.util import save_unknown_post
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler

log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post_ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[ContextFilter()]
)

#configure_root_logger('%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - [Search ID: %(search_id)s][Post ID: %(post_id)s][Subreddit: %(subreddit)s]- %(levelname)s: %(message)s', [SearchContextFilter()])

class SummonsHandlerTask(Task):
    def __init__(self):
        self.config = Config()
        self.redlock = get_redlock_factory(self.config)
        self.reddit = get_reddit_instance(self.config)
        self.reddit_manager = RedditManager(self.reddit)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        notification_svc = NotificationService(self.config)
        self.response_handler = ResponseHandler(self.reddit_manager, self.uowm, self.event_logger, source='summons',
                                                live_response=self.config.live_responses,
                                                notification_svc=notification_svc)
        dup_image_svc = DuplicateImageService(self.uowm, self.event_logger, self.reddit, config=self.config)
        response_builder = ResponseBuilder(self.uowm)
        self.summons_handler = SummonsHandler(self.uowm, dup_image_svc, self.reddit_manager, response_builder,
                                              self.response_handler, event_logger=self.event_logger,
                                              summons_disabled=False, notification_svc=notification_svc)


    def _get_log_adaptor(self):
        pass

class SubMonitorTask(Task):


    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.reddit_manager = RedditManager(self.reddit)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        event_logger = EventLogging(config=self.config)
        response_handler = ResponseHandler(self.reddit_manager, self.uowm, event_logger, source='submonitor', live_response=self.config.live_responses)
        dup_image_svc = DuplicateImageService(self.uowm, event_logger, self.reddit, config=self.config)
        response_builder = ResponseBuilder(self.uowm)
        self.sub_monitor = SubMonitor(dup_image_svc, self.uowm, self.reddit_manager, response_builder, response_handler, event_logger=event_logger, config=self.config)
        self.blacklisted_posts = []


@celery.task(bind=True, base=SubMonitorTask, serializer='pickle')
def sub_monitor_check_post(self, post_id: Text, monitored_sub: MonitoredSub):
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
            log.info('Post %s does exist, attempting to ingest', post_id)
            post = save_unknown_post(post_id, self.uowm, self.reddit)
            if not post:
                log.error('Failed to save post during monitor sub check')
                self.blacklisted_posts.append(post_id)
                return

    title_keywords = []
    if monitored_sub.title_ignore_keywords:
        title_keywords = monitored_sub.title_ignore_keywords.split(',')

    try:
        if not self.sub_monitor.should_check_post(
                post,
                monitored_sub.check_image_posts,
                monitored_sub.check_link_posts,
                title_keyword_filter=title_keywords
        ):
            return
    except Exception as e:
        log.error('')
    results = self.sub_monitor.check_submission(monitored_sub, post)
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


@celery.task(bind=True, base=SummonsHandlerTask, serializer='pickle', ignore_results=True, )
def process_summons(self, summons: Summons):
    try:
        update_log_context_data(log, {'trace_id': str(randint(100000, 999999)), 'post_id': summons.post.post_id, 'service': 'Summons'})
        with self.uowm.start() as uow:
            log.info('Starting summons %s ', summons.id)
            updated_summons = uow.summons.get_by_id(summons.id)
            if updated_summons and updated_summons.summons_replied_at:
                log.info('Summons %s already replied, skipping', summons.id)
                return
            try:
                with self.redlock.create_lock(f'summons_{summons.id}', ttl=120000):

                    try:
                        self.summons_handler.process_summons(summons)
                    except ResponseException as e:
                        if e.response.status_code == 429:
                            log.error('IP Rate limit hit.  Waiting')
                            time.sleep(60)
                            return
                    except AssertionError as e:
                        if 'code: 429' in str(e):
                            log.error('Too many requests from IP.  Waiting')
                            time.sleep(60)
                            return
                    except APIException as e:
                        if hasattr(e, 'error_type') and e.error_type == 'RATELIMIT':
                            log.error('Hit API rate limit for summons %s on sub %s.', summons.id, summons.post.subreddit)
                            return
                    except Exception as e:
                        log.exception('Unknown error')

                    # TODO - This sends completed summons events to influx even if they fail
                    summons_event = SummonsEvent(float((datetime.utcnow() - summons.summons_received_at).seconds),
                                                 summons.summons_received_at, summons.requestor, event_type='summons')
                    self.summons_handler._send_event(summons_event)
                    log.info('Finished summons %s', summons.id)
            except RedLockError:
                log.error('Summons %s already in process', summons.id)
                time.sleep(3)
    except Exception as e:
        log.exception('')