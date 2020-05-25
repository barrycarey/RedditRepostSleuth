import json
import time
from datetime import datetime
from json import JSONDecodeError

from celery import Task
from praw.exceptions import APIException
from prawcore import ResponseException
from redlock import RedLockError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.summonsevent import SummonsEvent
from redditrepostsleuth.core.model.repostresponse import SummonsResponse

from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.objectmapping import submission_to_post
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.util.redlock import redlock
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler


class SummonsHandlerTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = RedditManager(get_reddit_instance(self.config))
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger, source='summons')
        dup_image_svc = DuplicateImageService(self.uowm, self.event_logger, config=self.config)
        response_builder = ResponseBuilder(self.uowm)
        self.summons_handler = SummonsHandler(self.uowm, dup_image_svc, self.reddit, response_builder,
                                 self.response_handler, event_logger=self.event_logger, summons_disabled=False)

class SubMonitorTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = RedditManager(get_reddit_instance(self.config))
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        event_logger = EventLogging(config=self.config)
        response_handler = ResponseHandler(self.reddit, self.uowm, event_logger, source='submonitor')
        dup_image_svc = DuplicateImageService(self.uowm, event_logger, config=self.config)
        response_builder = ResponseBuilder(self.uowm)
        self.sub_monitor = SubMonitor(dup_image_svc, self.uowm, self.reddit, response_builder, response_handler, event_logger=event_logger, config=self.config)


@celery.task(bind=True, base=SubMonitorTask, serializer='pickle')
def sub_monitor_check_post(self, submission, monitored_sub):
    if self.sub_monitor.has_post_been_checked(submission.id):
        log.debug('Post %s has already been checked', submission.id)
        return

    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(submission.id)
        if not post:
            log.info('Post %s does exist, sending to ingest queue', submission.id)
            post = submission_to_post(submission)
            celery.send_task('redditrepostsleuth.core.celery.ingesttasks.save_new_post', args=[post],
                             queue='postingest')
            return

    title_keywords = []
    if monitored_sub.title_ignore_keywords:
        title_keywords = monitored_sub.title_ignore_keywords.split(',')

    if not self.sub_monitor.should_check_post(post, title_keyword_filter=title_keywords):
        return
    self.sub_monitor.check_submission(submission, monitored_sub, post)

@celery.task(bind=True, base=SubMonitorTask, serializer='pickle', ignore_results=True)
def process_monitored_sub(self, monitored_sub):
    try:
        subreddit = self.reddit.subreddit(monitored_sub.name)
        if not subreddit:
            log.error('Failed to get Subreddit %s', monitored_sub.name)
            return
        log.info('Loading all submissions from %s', monitored_sub.name)
        submissions = subreddit.new(limit=monitored_sub.search_depth)
        for submission in submissions:
            sub_monitor_check_post.apply_async((submission, monitored_sub), queue='submonitor')
        log.info('All submissions from %s sent to queue', monitored_sub.name)
    except ResponseException as e:
        if e.response.status_code == 429:
            log.error('IP Rate limit hit.  Waiting')
            time.sleep(60)
            return

@celery.task(bind=True, base=SummonsHandlerTask, serializer='pickle', ignore_results=True, )
def process_summons(self, s):
    with self.uowm.start() as uow:
        #summons = uow.summons.get_unreplied(limit=5)
        log.info('Starting summons %s on sub %s', s.id, s.subreddit)
        updated_summons = uow.summons.get_by_id(s.id)
        if updated_summons and updated_summons.summons_replied_at:
            log.info('Summons %s already replied, skipping', s.id)
            return
        try:
            with redlock.create_lock(f'summons_{s.id}', ttl=120000):
                post = uow.posts.get_by_post_id(s.post_id)
                if not post:
                    post = self.summons_handler.save_unknown_post(s.post_id)

                if not post:
                    response = SummonsResponse(summons=s)
                    response.message = 'Sorry, I\'m having trouble with this post. Please try again later'
                    log.info('Failed to ingest post %s.  Sending error response', s.post_id)
                    self.summons_handler._send_response(response)
                    return

                try:
                    self.summons_handler.process_summons(s, post)
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
                        log.error('Hit API rate limit for summons %s on sub %s.', s.id, s.subreddit)
                        return
                        #time.sleep(60)

                # TODO - This sends completed summons events to influx even if they fail
                summons_event = SummonsEvent(float((datetime.utcnow() - s.summons_received_at).seconds),
                                             s.summons_received_at, s.requestor, event_type='summons')
                self.summons_handler._send_event(summons_event)
                log.info('Finished summons %s', s.id)
        except RedLockError:
            log.error('Summons %s already in process', s.id)
            time.sleep(3)