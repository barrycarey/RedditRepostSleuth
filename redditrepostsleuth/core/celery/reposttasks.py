from time import perf_counter
from typing import List, Dict

import requests
from redlock import RedLockError
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.exception import NoIndexException, CrosspostRepostCheck, IngestHighMatchMeme
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.annoysearchevent import AnnoySearchEvent
from redditrepostsleuth.core.model.events.celerytask import BatchedEvent
from redditrepostsleuth.core.model.events.repostevent import RepostEvent
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.repostwrapper import RepostWrapper
from redditrepostsleuth.core.util.replytemplates import WATCH_NOTIFY_OF_MATCH
from redditrepostsleuth.core.util.reposthelpers import check_link_repost
from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AnnoyTask, SqlAlchemyTask, RedditTask
from redditrepostsleuth.core.celery.helpers.repost_image import find_matching_images, save_image_repost_result, \
    repost_watch_notify, check_for_post_watch
from redditrepostsleuth.core.db.databasemodels import Post, LinkRepost, RepostWatch


@celery.task(ignore_results=True)
def ingest_repost_check(post):
    if post.post_type == 'image':
        check_image_repost_save.apply_async((post,), queue='repost_image')
    elif post.post_type == 'link':
        link_repost_check.apply_async(([post],))

@celery.task(bind=True, base=AnnoyTask, serializer='pickle', ignore_results=True, autoretry_for=(RedLockError,NoIndexException, IngestHighMatchMeme), retry_kwargs={'max_retries': 20, 'countdown': 300})
def check_image_repost_save(self, post: Post) -> RepostWrapper:
    r = requests.head(post.url)
    if r.status_code != 200:
        log.info('Skipping image that is deleted %s', post.url)
        return

    if post.crosspost_parent:
        log.info('Post %sis a crosspost, skipping repost check', post.post_id)
        raise CrosspostRepostCheck('Post {} is a crosspost, skipping repost check'.format(post.post_id))

    result = find_matching_images(post, self.dup_service)

    save_image_repost_result(result, self.uowm)

    self.event_logger.save_event(RepostEvent(
        event_type='repost_found' if result.matches else 'repost_check',
        status='success',
        post_type='image',
        repost_of=result.matches[0].post.post_id if result.matches else None,

    ))
    watches = check_for_post_watch(result.matches, self.uowm)
    if watches and self.config.enable_repost_watch:
        notify_watch.apply_async((watches,), queue='watch_notify')

    return result


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def link_repost_check(self, posts, ):
    with self.uowm.start() as uow:
        for post in posts:
            repost = check_link_repost(post, self.uowm)
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
            uow.link_repost.add(new_repost)
            # uow.posts.update(repost.matches[0].post)
            # log_repost.apply_async((repost,))
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

        self.event_logger.save_event(
            BatchedEvent(event_type='repost_check', status='success', count=len(posts), post_type='link'))


@celery.task(bind=True, base=RedditTask, ignore_results=True)
def notify_watch(self, watches: List[Dict[ImageMatch, RepostWatch]]):
    repost_watch_notify(watches, self.reddit, self.response_handler)