import json
import time
from random import randint

import requests
from celery import Task
from praw.exceptions import RedditAPIException, APIException
from prawcore import TooManyRequests
from requests import ConnectionError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.task_logic.monitored_sub_task_logic import process_monitored_subreddit_submission
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException, RateLimitException, LoadSubredditException
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import update_log_context_data
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.submonitorsvc.monitored_sub_service import MonitoredSubService

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
        self.monitored_sub_svc = MonitoredSubService(dup_image_svc, self.uowm, self.reddit, response_builder, event_logger=event_logger, config=self.config)



@celery.task(
    bind=True,
    base=SubMonitorTask,
    serializer='pickle',
    autoretry_for=(TooManyRequests, RedditAPIException, NoIndexException, RateLimitException),
    retry_kwards={'max_retries': 3}
)
def sub_monitor_check_post(self, post_id: str, monitored_sub: MonitoredSub):
    try:
        update_log_context_data(log, {'trace_id': str(randint(100000, 999999)), 'post_id': post_id,
                                      'subreddit': monitored_sub.name, 'service': 'Subreddit_Monitor'})

        with self.uowm.start() as uow:
            process_monitored_subreddit_submission(post_id, self.monitored_sub_svc, uow)
    except Exception as e:
        log.exception('General failure')
        pass


@celery.task(
    bind=True,
    base=SubMonitorTask,
    serializer='pickle',
    ignore_results=True,
    autoretry_for=(LoadSubredditException,),
    retry_kwards={'max_retries': 3}
)
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
