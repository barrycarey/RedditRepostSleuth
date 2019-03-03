import json
import logging
import random
from datetime import datetime
from hashlib import md5
from time import perf_counter

import requests
from celery import Task
from redlock import RedLockError
from requests.exceptions import SSLError, ConnectionError, ReadTimeout, InvalidSchema, InvalidURL
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.celery import celery
from redditrepostsleuth.common.exception import ImageConversioinException, CrosspostRepostCheck
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.config.constants import USER_AGENTS
from redditrepostsleuth.config.replytemplates import WATCH_FOUND
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Comment, Post, ImageRepost, LinkRepost
from redditrepostsleuth.model.events.annoysearchevent import AnnoySearchEvent
from redditrepostsleuth.model.events.celerytask import BatchedEvent
from redditrepostsleuth.model.events.influxevent import InfluxEvent
from redditrepostsleuth.model.events.ingestsubmissionevent import IngestSubmissionEvent
from redditrepostsleuth.model.events.repostevent import RepostEvent
from redditrepostsleuth.model.repostwrapper import RepostWrapper
from redditrepostsleuth.service.CachedVpTree import CashedVpTree
from redditrepostsleuth.service.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.service.eventlogging import EventLogging
from redditrepostsleuth.util.helpers import get_reddit_instance
from redditrepostsleuth.util.imagehashing import generate_img_by_url, generate_dhash, set_image_hashes
from redditrepostsleuth.util.objectmapping import post_to_repost_match
from redditrepostsleuth.util.reposthelpers import sort_reposts, clean_repost_matches


@celery.task
def image_hash(data):
    try:
        img = generate_img_by_url(data['url'])
        data['hash'] = generate_dhash(img)
    except ImageConversioinException as e:
        data['delete'] = True

    return data

class EventLoggerTask(Task):
    def __init__(self):
        self.event_logger = EventLogging()

class SqlAlchemyTask(Task):

    def __init__(self):
        self.uowm = SqlAlchemyUnitOfWorkManager(db_engine)
        self.reddit = get_reddit_instance()
        self.event_logger = EventLogging()

class VpTreeTask(Task):
    def __init__(self):
        self.uowm = SqlAlchemyUnitOfWorkManager(db_engine)
        self.vptree_cache = CashedVpTree(self.uowm)

class AnnoyTask(Task):
    def __init__(self):
        self.uowm = SqlAlchemyUnitOfWorkManager(db_engine)
        self.dup_service = DuplicateImageService(self.uowm)
        self.reddit = get_reddit_instance()
        self.event_logger = EventLogging()

class RedditTask(Task):
    def __init__(self):
        self.reddit = get_reddit_instance()
        self.uowm = SqlAlchemyUnitOfWorkManager(db_engine)
        self.event_logger = EventLogging()

class RepostLogger(Task):
    def __init__(self):
        self.repost_log = logging.getLogger('error_log')
        self.repost_log.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s: %(message)s')
        handler = logging.FileHandler('repost.log')
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.repost_log.addHandler(handler)



@celery.task(bind=True, base=EventLoggerTask, ignore_results=True, serializer='pickle')
def log_event(self, event):
    self.event_logger.save_event(event)

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def delete_dups(self, objs):
    log.info('Starting delete batch')
    with self.uowm.start() as uow:
        for post in objs:
            dups = uow.image_repost.get_dups_by_post_id(post.post_id)
            if len(dups) > 1:
                keep = dups[0].id
                for dup in dups:
                    if dup.id != keep:
                        uow.image_repost.remove(dup)
                        log.info('deleting post %s', dup.post_id)
                uow.commit()

    log.info('Finished delete batch')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def link_repost_check(self, posts):
    with self.uowm.start() as uow:
        for post in posts:
            repost = RepostWrapper()
            repost.checked_post = post
            repost.matches = [post_to_repost_match(match, post.id) for match in uow.posts.find_all_by_url_hash(post.url_hash) if match.post_id != post.post_id]
            repost.matches = clean_repost_matches(repost)
            if not repost.matches:
                log.debug('Not matching linkes for post %s', post.post_id)
                post.checked_repost = True
                uow.posts.update(post)
                uow.commit()
                continue

            log.info('Found %s matching links', len(repost.matches))
            log.info('Creating Link Repost. Post %s is a repost of %s', post.post_id, repost.matches[0].post.post_id)
            """
            

            log.debug('Checked Link %s (%s): %s', post.post_id, post.created_at, post.url)
            for match in repost.matches:
                log.debug('Matching Link: %s (%s)  - %s', match.post.post_id, match.post.created_at, match.post.url)
            log.info('Creating Link Repost. Post %s is a repost of %s', post.post_id, repost.matches[0].post.post_id)
            """
            repost_of = repost.matches[0].post
            new_repost = LinkRepost(post_id=post.post_id, repost_of=repost_of.post_id)
            repost_of.repost_count += 1
            post.checked_repost = True
            uow.posts.update(post)
            uow.repost.add(new_repost)
            #uow.posts.update(repost.matches[0].post)
            log_repost.apply_async((repost,))
            try:
                uow.commit()
                self.event_logger.save_event(RepostEvent(event_type='repost_found', status='success',
                                                         repost_of=repost.matches[0].post.post_id,
                                                         post_type=post.post_type))
            except IntegrityError as e:
                uow.rollback()
                log.exception('Error saving link repost', exc_info=True)
                self.event_logger.save_event(RepostEvent(event_type='repost_found', status='error',
                                                         repost_of=repost.matches[0].post.post_id,
                                                         post_type=post.post_type))







        self.event_logger.save_event(BatchedEvent(event_type='repost_check', status='success', count=len(posts), post_type='link'))



@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def save_new_comment(self, comment):
    with self.uowm.start() as uow:
        new_comment = Comment(body=comment.body, comment_id=comment.id)
        uow.comments.add(new_comment)
        try:
            uow.commit()
            self.event_logger.save_event(InfluxEvent(event_type='ingest_comment', status='success'))
        except Exception as e:
            self.event_logger.save_event(InfluxEvent(event_type='ingest_comment', status='error'))


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def process_repost_annoy(self, repost: RepostWrapper):
    # TODO: Break down into smaller chunks
    print('Processing task for repost ' + repost.checked_post.post_id)
    with self.uowm.start() as uow:

        repost.checked_post.checked_repost = True
        if not repost.matches:
            log.debug('Post %s has no matches', repost.checked_post.post_id)
            uow.posts.update(repost.checked_post)
            uow.commit()
            self.event_logger.save_event(BatchedEvent(event_type='repost_check', status='success', count=1, post_type=repost.checked_post.post_type))
            return

        # Get the post object for each match
        for match in repost.matches:
            match.post = uow.posts.get_by_id(match.match_id)

        repost.matches = clean_repost_matches(repost)

        if len(repost.matches) > 0:

            final_matches = sort_reposts(repost.matches)

            log.debug('Checked Image (%s): %s', repost.checked_post.created_at, repost.checked_post.url)
            for match in final_matches:
                log.debug('Matching Image: %s (%s) (Hamming: %s - Annoy: %s): %s', match.post.post_id, match.post.created_at, match.hamming_distance, match.annoy_distance, match.post.url)
            log.info('Creating repost. Post %s is a repost of %s', repost.checked_post.url, final_matches[0].post.url)

            new_repost = ImageRepost(post_id=repost.checked_post.post_id,
                                     repost_of=final_matches[0].post.post_id,
                                     hamming_distance=final_matches[0].hamming_distance,
                                     annoy_distance=final_matches[0].annoy_distance)
            final_matches[0].post.repost_count += 1
            uow.posts.update(final_matches[0].post)
            uow.repost.add(new_repost)
            repost.matches = final_matches
            log_repost.apply_async((repost,), queue='repostlog')

            self.event_logger.save_event(
                RepostEvent(event_type='repost_found', status='success', post_type=repost.checked_post.post_type))

            check_repost_watch.apply_async((new_repost,), queue='test')

        uow.posts.update(repost.checked_post)

        uow.commit()

        self.event_logger.save_event(BatchedEvent(event_type='repost_check', status='success', count=1,
                                                  post_type=repost.checked_post.post_type))




@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def check_repost_watch(self, repost):
    with self.uowm.start() as uow:
        watch = uow.repostwatch.get_by_post_id(repost.repost_of)
        if not watch:
            log.debug('No repost watch for post %s', repost.repost_of)
            return
        repost_obj = uow.posts.get_by_post_id(repost.post_id)
    log.info('Post %s has an active watch for user %s', watch.post_id, watch.user)
    reddit = get_reddit_instance()
    if watch.response_type == 'message':
        log.info('Sending private message to %s', watch.user)
        reddit.redditor(watch.user).message('Repost Sleuth Watch Alert', WATCH_FOUND.format(user=watch.user, repost_url=repost_obj.shortlink))



@celery.task(bind=True, base=RepostLogger, ignore_results=True, serializer='pickle')
def log_repost(self, repost: RepostWrapper):
    self.repost_log.info('---------------------------------------------')
    if repost.checked_post.post_type == 'image':

        self.repost_log.info('Original (%s): %s - %s', repost.checked_post.created_at, repost.checked_post.post_id, repost.checked_post.shortlink)
        for match in repost.matches:
            self.repost_log.info('Match (%s): %s - %s (Ham: %s - Annoy %s)', match.post.created_at, match.post.post_id, match.post.shortlink, match.hamming_distance, match.annoy_distance)
    else:
        self.repost_log.info('Original Link %s (%s): %s', repost.checked_post.post_id, repost.checked_post.created_at, repost.checked_post.url)
        for match in repost.matches:
            log.debug('Matching Link: %s (%s)  - %s', match.post.post_id, match.post.created_at, match.post.url)

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def hash_link_url(self, id):
    with self.uowm.start() as uow:
        post = uow.posts.get_by_id(id)
        if not post:
            log.error('Didnt get post with id %s', id)
        url_hash = md5(post.url.encode('utf-8'))
        post.url_hash = url_hash.hexdigest()
        uow.commit()
        self.event_logger.save_event(InfluxEvent(event_type='hash_url', post_id=post.post_id))

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def check_deleted_posts(self, posts):
    with self.uowm.start() as uow:
        for i in posts:
            post = uow.posts.get_by_id(i.id)
            log.debug('Deleted Check: Post ID %s, URL %s', post.post_id, post.url)
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            try:
                r = requests.head(post.url, timeout=20, headers=headers)
                if r.status_code == 404 and post.post_type == 'image':
                    log.debug('Deleting removed post (%s)', str(post))
                    uow.posts.remove(post)
                post.last_deleted_check = datetime.utcnow()
                uow.posts.update(post)
            except (ConnectionError, SSLError, ReadTimeout, InvalidSchema, InvalidURL) as e:
                if isinstance(e, SSLError):
                    log.error('Failed to verify SSL for: %s', post.url)
                    post.last_deleted_check = datetime.utcnow()
                    uow.posts.update(post)

                elif isinstance(e, ConnectionError) or isinstance(e, ReadTimeout) or isinstance(e, InvalidSchema) or isinstance(e, InvalidURL):
                    log.error('Failed to connect to: %s', post.url)
                    post.bad_url = True
                    post.last_deleted_check = datetime.utcnow()
                    uow.posts.update(post)
                else:
                    #uow.rollback()
                    log.exception('Exception with deleted image cleanup for URL: %s ', post.url, exc_info=True)
                    print('')


        try:
            log.info('Saving batch of delete checks')
            uow.commit()
            status = 'success'

        except Exception as e:
            uow.rollback()
            log.error('Commit failed: %s', str(e))
            status = 'error'

        self.event_logger.save_event(BatchedEvent(count=len(posts), event_type='delete_check', status=status))


@celery.task(bind=True, base=AnnoyTask, serializer='pickle', autoretry_for=(RedLockError,))
def find_matching_images_annoy(self, post: Post) -> RepostWrapper:
    if post.crosspost_parent:
        log.info('Post %sis a crosspost, skipping repost check', post.post_id)
        raise CrosspostRepostCheck('Post {} is a crosspost, skipping repost check'.format(post.post_id))

    start = perf_counter()
    result = RepostWrapper()
    result.checked_post = post
    result.matches = self.dup_service.check_duplicate(post)
    log.debug('Found %s matching images', len(result.matches))
    search_time = perf_counter() - start
    self.event_logger.save_event(AnnoySearchEvent(search_time, self.dup_service.index_size, event_type='find_matching_images'))
    return result

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
def save_new_post(self, post):
    # TODO - This whole mess needs to be cleaned up

    with self.uowm.start() as uow:
        uow.posts.add(post)

        if post.post_type == 'image':
            try:
                set_image_hashes(post)
            except ImageConversioinException as e:
                log.error('Failed to get image hashes on new post')
                pass
        elif post.post_type == 'link':
            url_hash = md5(post.url.encode('utf-8'))
            post.url_hash = url_hash.hexdigest()
            log.info('Set URL hash for post %s', post.post_id)

        try:
            uow.commit()
            ingest_repost_check.apply_async((post,))
            event = IngestSubmissionEvent(event_type='ingest_post', status='success', post_id=post.post_id, queue='post',
                                      post_type=post.post_type)

        except Exception as e:

                event = IngestSubmissionEvent(event_type='ingest_post', status='error', post_id=post.post_id, queue='post',
                                      post_type=post.post_type)

        #log_event.apply_async((event,), queue='logevent')



@celery.task(ignore_results=True)
def ingest_repost_check(post):
    if post.post_type == 'image' and config.check_new_images_for_repost:
        (find_matching_images_annoy.s(post) | process_repost_annoy.s()).apply_async()
    elif post.post_type == 'link' and config.check_new_links_for_repost:
        link_repost_check.apply_async(([post],))

@celery.task(bind=True, base=RedditTask, ignore_reseults=True)
def update_cross_post_parent(self, ids):
    submissions = self.reddit.info(fullnames=ids)
    with self.uowm.start() as uow:
        for submission in submissions:
            post = uow.posts.get_by_post_id(submission.id)
            if not post:
                continue
            post.crosspost_parent = submission.__dict__.get('crosspost_parent', None)
            post.crosspost_checked = True
        try:
            uow.commit()
            log.info('Saved crosspost batch')
            self.event_logger.save_event(
                InfluxEvent(event_type='crosspost_check', status='success', queue='post'))
        except Exception as e:
            log.exception('Problem saving cross post')
            self.event_logger.save_event(InfluxEvent(event_type='crosspost_check', status='error', queue='post', rate_limit=self.reddit.auth.limits['remaining']))

        print(self.reddit.auth.limits)


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def update_crosspost_parent_api(self, ids):
    r = requests.post('http://sr2.plxbx.com:8888/crosspost', data={'data': ids})
    results = json.loads(r.text)
    if len(results) < 100:
        log.error('Less than 100 results: Total: %s', len(results))
    with self.uowm.start() as uow:
        for result in results:
            post = uow.posts.get_by_post_id(result['id'])
            post.selftext = result['selftext']
            post.shortlink = result['shortlink']
            post.crosspost_checked = True
            uow.commit()
        self.event_logger.save_event(
            BatchedEvent(event_type='selftext', status='success', count=len(ids), post_type='link'))
        log.debug('Saved batch of crosspost')
