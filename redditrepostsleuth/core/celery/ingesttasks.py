import json
import logging
from hashlib import md5
from random import randint
from time import perf_counter

import requests
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import Post, PostHash, ImagePost
from redditrepostsleuth.core.exception import InvalidImageUrlException, ImageConversionException
from redditrepostsleuth.core.logfilters import IngestContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.util.helpers import update_log_context_data
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.objectmapping import pushshift_to_post
from redditrepostsleuth.ingestsvc.util import pre_process_post

log = logging.getLogger('redditrepostsleuth')
log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post Type=%(post_type)s Post ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[IngestContextFilter()]
)

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', autoretry_for=(ConnectionError,InvalidImageUrlException), retry_kwargs={'max_retries': 20, 'countdown': 300})
def save_new_post(self, post: Post):
    update_log_context_data(log, {'post_type': post.post_type, 'post_id': post.post_id,
                                  'subreddit': post.subreddit, 'service': 'Ingest',
                                  'trace_id': str(randint(1000000, 9999999))})
    try:
        with self.uowm.start() as uow:
            existing = uow.posts.get_by_post_id(post.post_id)
            if existing:
                return
            log.debug('Post %s: Ingesting', post.post_id)
            # post = pre_process_post(post, self.uowm, self.config.image_hash_api)
            if post:
                monitored_sub = uow.monitored_sub.get_by_sub(post.subreddit)
                if monitored_sub:
                    log.info('Sending ingested post to monitored sub queue')
                    celery.send_task('redditrepostsleuth.core.celery.response_tasks.sub_monitor_check_post',
                                     args=[post.post_id, monitored_sub],
                                     queue='submonitor')

                log.debug('Sent post to repost queue', )

                try:
                    url_hash = md5(post.url.encode('utf-8'))
                    post.url_hash = url_hash.hexdigest()
                except Exception as e:
                    return

                if post.post_type == 'image':
                    try:
                        image_hashes = get_image_hashes(post.url)
                        post.hash_1 = image_hashes['dhash_h']
                        post.hash_2 = image_hashes['dhash_v']
                        post.image_post = ImagePost(dhash_h=image_hashes['dhash_h'], dhash_v=image_hashes['dhash_v'], created_at=post.created_at)
                    except ImageConversionException:
                        log.exception('Failed to convert image')
                        return
                    except Exception as e:
                        log.exception('Failed to hash images')

                uow.posts.add(post)
                try:
                    uow.commit()
                    ingest_repost_check.apply_async((post, self.config), queue='repost')
                except (IntegrityError) as e:
                    log.error('Failed to save duplicate post')
                except Exception as e:
                    print(e)
    except Exception as e:
        print('')



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
            post = pushshift_to_post(submission)
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
            post = pushshift_to_post(submission)
            log.debug('Saving pushshift post: %s', submission['id'])
            save_new_post.apply_async((post,), queue='pushshift_ingest')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def set_image_post_created_at(self, data):
    start = perf_counter()
    with self.uowm.start() as uow:
        for image_post in data:

            post = uow.posts.get_by_post_id(image_post.post_id)
            if not post:
                continue
            image_post.created_at = post.created_at
            #uow.image_post.update(image_post)

        uow.image_post.bulk_save(data)

        uow.commit()
        print(f'Last ID {data[-1].id} - Time: {perf_counter() - start}')
    #print('Finished Batch')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def ingest_id_batch(self, ids_to_get):
    r = requests.get(f'{self.config.util_api}/reddit/submissions', params={'submission_ids': ','.join(ids_to_get)})
    results = json.loads(r.text)
    save_pushshift_results.apply_async((results,), queue='pushshift')