import json
import logging
from random import randint
from time import perf_counter

import requests

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import RedditImagePostCurrent, Post
from redditrepostsleuth.core.exception import InvalidImageUrlException
from redditrepostsleuth.core.logfilters import IngestContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.util.helpers import update_log_context_data
from redditrepostsleuth.core.util.objectmapping import reddit_submission_to_post
from redditrepostsleuth.ingestsvc.util import pre_process_post

log = logging.getLogger('redditrepostsleuth')
log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post Type=%(post_type)s Post ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[IngestContextFilter()]
)


@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', autoretry_for=(ConnectionError,InvalidImageUrlException), retry_kwargs={'max_retries': 20, 'countdown': 300})
def save_new_post(self, post: Post):
    try:
        update_log_context_data(log, {'post_type': post.post_type, 'post_id': post.post_id,
                                      'subreddit': post.subreddit, 'service': 'Ingest',
                                      'trace_id': str(randint(1000000, 9999999))})
        with self.uowm.start() as uow:
            existing = uow.posts.get_by_post_id(post.post_id)
            if existing:
                return
            log.debug('Post %s: Ingesting', post.post_id)
            post = pre_process_post(post, self.uowm)

            if not post:
                return

            monitored_sub = uow.monitored_sub.get_by_sub(post.subreddit)
            if monitored_sub and monitored_sub.active:
                log.info('Sending ingested post to monitored sub queue')
                celery.send_task('redditrepostsleuth.core.celery.response_tasks.sub_monitor_check_post',
                                 args=[post.post_id, monitored_sub],
                                 queue='submonitor')
            ingest_repost_check.apply_async((post, self.config), queue='repost')

    except Exception as e:
        log.exception('')


@celery.task(ignore_results=True)
def ingest_repost_check(post, config):
    if post.post_type == 'image' and config.repost_image_check_on_ingest:
        celery.send_task('redditrepostsleuth.core.celery.reposttasks.check_image_repost_save', args=[post], queue='repost_image')
    elif post.post_type == 'link' and config.repost_link_check_on_ingest:
        celery.send_task('redditrepostsleuth.core.celery.reposttasks.link_repost_check', args=[[post]], queue='repost_link')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def save_pushshift_results(self, data):
    with self.uowm.start() as uow:
        for submission in data:
            existing = uow.posts.get_by_post_id(submission['id'])
            if existing:
                log.debug('Skipping pushshift post: %s', submission['id'])
                continue
            post = reddit_submission_to_post(submission)
            log.debug('Saving pushshift post: %s', submission['id'])
            save_new_post.apply_async((post,), queue='postingest')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def save_pushshift_results_archive(self, data):
    with self.uowm.start() as uow:
        for submission in data:
            existing = uow.posts.get_by_post_id(submission['id'])
            if existing:
                log.debug('Skipping pushshift post: %s', submission['id'])
                continue
            post = reddit_submission_to_post(submission)
            log.debug('Saving pushshift post: %s', submission['id'])
            save_new_post.apply_async((post,), queue='pushshift_ingest')


