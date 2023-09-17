from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.celery.task_logic.ingest_task_logic import pre_process_post
from redditrepostsleuth.core.exception import InvalidImageUrlException, GalleryNotProcessed, ImageConversionException, \
    ImageRemovedException
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.util.objectmapping import reddit_submission_to_post

log = get_configured_logger('redditrepostsleuth')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', autoretry_for=(ConnectionError,ImageConversionException,GalleryNotProcessed), retry_kwargs={'max_retries': 10, 'countdown': 300})
def save_new_post(self, submission: dict):

    # TODO: temp fix until I can fix imgur gifs
    if 'imgur' in submission['url'] and 'gifv' in submission['url']:
        return

    with self.uowm.start() as uow:
        existing = uow.posts.get_by_post_id(submission['id'])
        if existing:
            return

        try:
            post = pre_process_post(submission)
        except (ImageRemovedException, InvalidImageUrlException) as e:
            return

        if not post:
            return

        monitored_sub = uow.monitored_sub.get_by_sub(post.subreddit)
        if monitored_sub and monitored_sub.active:
            log.info('Sending ingested post to monitored sub queue')
            celery.send_task('redditrepostsleuth.core.celery.response_tasks.sub_monitor_check_post',
                             args=[post.post_id, monitored_sub],
                             queue='submonitor')

        try:
            uow.posts.add(post)
            uow.commit()
        except IntegrityError:
            log.warning('Post already exists in database. %s', post.post_id)
            return
        except Exception as e:
            log.exception('Database save failed: %s', str(e), exc_info=False)
            return

    if post.post_type_id == 1:
        celery.send_task('redditrepostsleuth.core.celery.tasks.repost_tasks.check_for_text_repost_task', args=[post])
    elif post.post_type_id == 2:
        celery.send_task('redditrepostsleuth.core.celery.tasks.repost_tasks.check_image_repost_save', args=[post])
    elif post.post_type_id == 3:
        celery.send_task('redditrepostsleuth.core.celery.tasks.repost_tasks.link_repost_check', args=[post])

    celery.send_task('redditrepostsleuth.core.celery.admin_tasks.check_user_for_only_fans', args=[post.author])



@celery.task
def save_new_posts(posts: list[dict]) -> None:
    for post in posts:
        save_new_post.apply_async((post,))

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




