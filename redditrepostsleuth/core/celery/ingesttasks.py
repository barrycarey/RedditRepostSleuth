from time import perf_counter

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import RedditImagePostCurrent
from redditrepostsleuth.core.exception import InvalidImageUrlException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.objectmapping import pushshift_to_post
from redditrepostsleuth.ingestsvc.util import pre_process_post


@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', autoretry_for=(ConnectionError,InvalidImageUrlException), retry_kwargs={'max_retries': 20, 'countdown': 300})
def save_new_post(self, post):
    with self.uowm.start() as uow:
        existing = uow.posts.get_by_post_id(post.post_id)
        if existing:
            return
        log.debug('Post %s: Ingesting', post.post_id)
        post = pre_process_post(post, self.uowm, self.config.image_hash_api)
        if post:
            ingest_repost_check.apply_async((post,self.config), queue='repost')
            log.debug('Post %s: Sent post to repost queue', post.post_id)


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
def populate_image_post_current(self, data):
    batch = []
    with self.uowm.start() as uow:
        for post in data:
            existing = uow.image_post_current.get_by_post_id(post.post_id)
            if existing:
                continue
            new = RedditImagePostCurrent(
                post_id=post.post_id,
                created_at=post.created_at,
                dhash_h=post.dhash_h,
                dhash_v=post.dhash_v
            )
            batch.append(new)

        uow.image_post_current.bulk_save(batch)
        uow.commit()
        print('Saved batch')