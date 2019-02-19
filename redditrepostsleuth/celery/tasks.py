import random
from typing import List

import requests
from celery import Task
from datetime import datetime

from distance import hamming
from hashlib import md5

from redlock import RedLockError
from requests.exceptions import SSLError, ConnectionError, ReadTimeout

from redditrepostsleuth.celery import celery
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.config import config
from redditrepostsleuth.config.constants import USER_AGENTS
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Reposts, Comment, Post, ImageRepost
from redditrepostsleuth.model.hashwrapper import HashWrapper
from redditrepostsleuth.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.model.influxevent import InfluxEvent
from redditrepostsleuth.model.ingestsubmissionevent import IngestSubmissionEvent
from redditrepostsleuth.service.CachedVpTree import CashedVpTree
from redditrepostsleuth.service.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.service.eventlogging import EventLogging

from redditrepostsleuth.util.helpers import get_reddit_instance, get_influx_instance
from redditrepostsleuth.util.imagehashing import generate_img_by_url, generate_dhash, find_matching_images_in_vp_tree, \
    get_bit_count, set_image_hashes
from redditrepostsleuth.util.objectmapping import post_to_hashwrapper
from redditrepostsleuth.util.reposthelpers import filter_matching_images, clean_reposts, get_crosspost_parent
from redditrepostsleuth.util.vptree import VPTree


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
        self.event_logger = EventLogging()


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def temp_hash_image(self, posts):
    with self.uowm.start() as uow:
        for post in posts:
            set_image_hashes(post)
            uow.posts.update(post)
        log.debug('Saving batch of hashes')
        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def set_bit_count(self, posts):
    with self.uowm.start() as uow:
        for post in posts:
            log.debug('Getting bits for post %s', post.post_id)
            if not post.image_hash or post.images_bits_set:
                continue
            try:
                img = generate_img_by_url(post.url)
            except Exception:
                log.error('Problem getting imgage')
                uow.posts.remove(post)
                uow.commit()
                continue
            post.images_bits_set = get_bit_count(img)
            uow.posts.update(post)
        uow.commit()

@celery.task(bind=True, base=RedditTask)
def remove_cross_posts(self, post: HashWrapper):
    if len(post.occurances < 2):
        log.info('Returning hash wrapper with 1 occurance')
        return post

    for post in post.occurances:
        submission = self.reddit.submission(id=post.post_id)
        if submission:
            try:
                post.crosspost_parent = submission.crosspost_parent
                log.info('Adding cross post parent %s to post %s', post.crosspost_parent, post.post_id)
            except AttributeError:
                pass

    return post

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def save_new_comment(self, comment):
    with self.uowm.start() as uow:
        new_comment = Comment(body=comment.body, comment_id=comment.id)
        uow.comments.add(new_comment)
        uow.commit()
        self.event_logger.save_event(InfluxEvent(event_type='ingest_comment'))


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def hash_image_and_save(self, post_id):
    log.debug('Hashing post %s', post_id)
    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(post_id)
        if not post:
            log.error('Cannot find post with ID %s', post_id)
        try:
            img = generate_img_by_url(post.url)
            result = generate_dhash(img)
            post.image_hash = result['hash']
            post.images_bits_set = result['bits_set']
        except ImageConversioinException as e:
            return
        uow.commit()


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def process_reposts(self, post: HashWrapper):
    print('Processing task for repost ' + post.post_id)
    with self.uowm.start() as uow:
        repost = uow.posts.get_by_post_id(post.post_id)
        repost.checked_repost = True
        if len(post.occurances) <= 1:
            log.debug('Post %s has no matches', post.post_id)
            uow.commit()
            return
        occurances = [uow.posts.get_by_post_id(p[1].post_id) for p in post.occurances]
        results = filter_matching_images(occurances, repost)
        results = clean_reposts(results)
        if len(results) > 0:
            print('Original: http://reddit.com' + repost.perma_link)

            log.error('Checked Repost - %s - (%s): http://reddit.com%s', repost.post_id, str(repost.created_at),
                      repost.perma_link)
            log.error('Oldest Post - %s - (%s): http://reddit.com%s', results[0].post_id,
                      str(results[0].created_at), results[0].perma_link)
            for p in results:
                log.error('%s - %s: http://reddit.com/%s', p.post_id, str(p.created_at), p.perma_link)

            new_repost = Reposts(post_id=post.post_id, repost_of=results[0].post_id, post_type='image')
            uow.repost.add(new_repost)
            uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def process_repost_annoy(self, repost: ImageRepostWrapper):
    # TODO: Break down into smaller chunks
    print('Processing task for repost ' + repost.checked_post.post_id)
    with self.uowm.start() as uow:

        if not repost.checked_post.crosspost_checked:
            log.debug('Checking repost cross post for ID %s', repost.checked_post.post_id)
            parent = get_crosspost_parent(repost.checked_post, self.reddit)
            repost.checked_post.crosspost_checked = True
            if parent:
                repost.checked_post.crosspost_parent = parent
                repost.checked_post.checked_repost = True
                uow.posts.update(repost.checked_post)
                uow.commit()
                self.event_logger.save_event(InfluxEvent(event_type='repost_check', status='success'))
                return

        repost.checked_post.checked_repost = True
        if not repost.matches:
            log.debug('Post %s has no matches', repost.checked_post.post_id)
            uow.posts.update(repost.checked_post)
            uow.commit()
            self.event_logger.save_event(InfluxEvent(event_type='repost_check', status='success'))
            return

        # Get the post object for each match
        for match in repost.matches:
            match.post = uow.posts.get_by_id(match.match_id)

        log.debug('Matches before cleaning: %s', len(repost.matches))
        clean_reposts(repost)
        log.debug('Matches after cleaning: %s', len(repost.matches))

        if len(repost.matches) > 0:
            # TODO: Move all crosspost logic to reposthelpers
            final_matches = []
            for match in repost.matches:
                if match.post.crosspost_checked:
                    log.debug('Crosspost already checked, adding to final results')
                    final_matches.append(match)
                    continue
                match.post.crosspost_parent = get_crosspost_parent(match.post, self.reddit)
                match.post.crosspost_checked = True
                if match.post.crosspost_parent:
                    log.debug('Matching post %s is a crosspost, removing from matches', match.post.post_id)
                else:
                    final_matches.append(match)

                uow.posts.update(match.post)
                uow.commit()

            if final_matches:
                log.debug('Checked Image: %s', repost.checked_post.url)
                for match in final_matches:
                    log.debug('Matching Image (%s) (Hamming: %s - Annoy: %s): %s', match.post.created_at, match.hamming_distance, match.annoy_distance, match.post.url)
                log.info('Creating repost. Post %s is a repost of %s', repost.checked_post.url, final_matches[0].post.url)

                new_repost = ImageRepost(post_id=repost.checked_post.post_id,
                                         repost_of=final_matches[0].post.post_id,
                                         hamming_distance=final_matches[0].hamming_distance,
                                         annoy_distance=final_matches[0].annoy_distance)
                uow.repost.add(new_repost)
                uow.commit()
        uow.posts.update(repost.checked_post)
        uow.commit()
        self.event_logger.save_event(InfluxEvent(event_type='repost_check', status='success'))


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
        for post in posts:
            log.debug('Deleted Check: Post ID %s, URL %s', post.post_id, post.url)
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            try:
                r = requests.head(post.url, timeout=20, headers=headers)
                if r.status_code == 404 and post.post_type == 'image':
                    log.debug('Deleting removed post (%s)', str(post))
                    uow.posts.remove(post)
                post.last_deleted_check = datetime.utcnow()
                uow.posts.update(post)
            except (ConnectionError, SSLError, ReadTimeout) as e:
                if isinstance(e, SSLError):
                    log.error('Failed to verify SSL for: %s', post.url)
                    post.last_deleted_check = datetime.utcnow()
                    uow.posts.update(post)

                elif isinstance(e, ConnectionError) or isinstance(e, ReadTimeout):
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
            for post in posts:
                self.event_logger.save_event(InfluxEvent(event_type='delete_check', status='success'))
        except Exception as e:
            uow.rollback()
            log.error('Commit failed: %s', str(e))
            self.event_logger.save_event(InfluxEvent(event_type='delete_check', status='error'))


@celery.task(bind=True, base=VpTreeTask, serializer='pickle')
def find_matching_images_task(self, hash):
    hash.occurances = find_matching_images_in_vp_tree(self.vptree_cache.get_tree, hash.image_hash, hamming_distance=config.hamming_distance)
    return hash


@celery.task(bind=True, base=AnnoyTask, serializer='pickle', autoretry_for=(RedLockError,))
def find_matching_images_annoy(self, post: Post) -> ImageRepostWrapper:
    result = ImageRepostWrapper()
    result.checked_post = post
    result.matches = self.dup_service.check_duplicate(post)
    log.debug('Found %s matching images', len(result.matches))
    self.event_logger.save_event(InfluxEvent(event_type='find_matching_images', post_id=post.post_id))
    return result

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
def save_new_post(self, post):
    # TODO - This whole mess needs to be cleaned up
    #post = postdto_to_post(postdto)
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
            self.event_logger.save_event(
                IngestSubmissionEvent(event_type='ingest_post', status='success', post_id=post.post_id, queue='post',
                                      post_type=post.post_type))
        except Exception as e:
            self.event_logger.save_event(
                IngestSubmissionEvent(event_type='ingest_post', status='error', post_id=post.post_id, queue='post',
                                      post_type=post.post_type))



@celery.task(serializer='pickle')
def build_vp_tree(points):
    return VPTree(points, lambda x,y: hamming(x,y))

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True)
def update_cross_post_parent(self, sub_id):
    reddit = get_reddit_instance()
    sub = reddit.submission(id=sub_id)
    if not sub:
        print('No submission found')
        return

    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(sub.id)
        if post:
            try:
                post.crosspost_parent = sub.crosspost_parent
            except AttributeError as e:
                pass
            post.crosspost_checked = True
            uow.commit()

