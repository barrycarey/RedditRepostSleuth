from time import perf_counter
from typing import List, Dict, NoReturn

import requests
from redlock import RedLockError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AnnoyTask, RedditTask, RepostTask
from redditrepostsleuth.core.celery.helpers.repost_image import save_image_repost_result, \
    repost_watch_notify, check_for_post_watch
from redditrepostsleuth.core.db.databasemodels import Post, LinkRepost, RepostWatch
from redditrepostsleuth.core.exception import NoIndexException, IngestHighMatchMeme
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.celerytask import BatchedEvent
from redditrepostsleuth.core.model.events.repostevent import RepostEvent
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.util.helpers import get_default_link_search_settings
from redditrepostsleuth.core.util.repost_helpers import get_link_reposts, filter_search_results


@celery.task(ignore_results=True)
def ingest_repost_check(post):
    if post.post_type == 'image':
        check_image_repost_save.apply_async((post,), queue='repost_image')
    elif post.post_type == 'link':
        link_repost_check.apply_async(([post],))


@celery.task(bind=True, base=AnnoyTask, serializer='pickle', ignore_results=True, autoretry_for=(RedLockError,NoIndexException, IngestHighMatchMeme), retry_kwargs={'max_retries': 20, 'countdown': 300})
def check_image_repost_save(self, post: Post) -> NoReturn:

    r = requests.head(post.url)
    if r.status_code != 200:
        log.info('Skipping image that is deleted %s', post.url)
        return

    search_results = self.dup_service.check_image(
        post.url,
        post=post,
        source='ingest_repost'
    )

    save_image_repost_result(search_results, self.uowm, source='ingest', high_match_check=True)

    self.event_logger.save_event(RepostEvent(
        event_type='repost_found' if search_results.matches else 'repost_check',
        status='success',
        post_type='image',
        repost_of=search_results.matches[0].post.post_id if search_results.matches else None,

    ))

    watches = check_for_post_watch(search_results.matches, self.uowm)
    if watches and self.config.enable_repost_watch:
        notify_watch.apply_async((watches, post), queue='watch_notify')

@celery.task(bind=True, base=RepostTask, ignore_results=True, serializer='pickle')
def link_repost_check(self, posts, ):
    with self.uowm.start() as uow:
        for post in posts:
            """
            if post.url_hash == '540f1167d27dcca2ea2772443beb5c79':
                continue
            """
            if post.url_hash in self.link_blacklist:
                log.info('Skipping blacklisted URL hash %s', post.url_hash)
                continue

            log.debug('Checking URL for repost: %s', post.url_hash)
            search_results = get_link_reposts(post.url, self.uowm, get_default_link_search_settings(self.config),
                                              post=post)

            if len(search_results.matches) > 10000:
                log.info('Link hash %s shared %s times. Adding to blacklist', post.url_hash, len(search_results.matches))
                self.link_blacklist.append(post.url_hash)
                self.notification_svc.send_notification(f'URL has been shared {len(search_results.matches)} times. Adding to blacklist. \n\n {post.url}')

            search_results = filter_search_results(
                search_results,
                uitl_api=f'{self.config.util_api}/maintenance/removed'
            )
            search_results.search_times.stop_timer('total_search_time')
            log.info('Link Query Time: %s', search_results.search_times.query_time)
            if not search_results.matches:
                log.debug('Not matching linkes for post %s', post.post_id)
                post.checked_repost = True
                uow.posts.update(post)
                uow.commit()
                continue

            log.info('Found %s matching links', len(search_results.matches))
            log.info('Creating Link Repost. Post %s is a repost of %s', post.post_id, search_results.matches[0].post.post_id)
            repost_of = search_results.matches[0].post
            new_repost = LinkRepost(post_id=post.post_id, repost_of=repost_of.post_id, author=post.author, source='ingest', subreddit=post.subreddit)
            repost_of.repost_count += 1
            post.checked_repost = True
            uow.posts.update(post)
            uow.link_repost.add(new_repost)

            try:
                uow.commit()
                self.event_logger.save_event(RepostEvent(event_type='repost_found', status='success',
                                                         repost_of=search_results.matches[0].post.post_id,
                                                         post_type=post.post_type))
            except IntegrityError as e:
                uow.rollback()
                log.exception('Error saving link repost', exc_info=True)
                self.event_logger.save_event(RepostEvent(event_type='repost_found', status='error',
                                                         repost_of=search_results.matches[0].post.post_id,
                                                         post_type=post.post_type))
        self.event_logger.save_event(
            BatchedEvent(event_type='repost_check', status='success', count=len(posts), post_type='link'))




@celery.task(bind=True, base=RedditTask, ignore_results=True)
def notify_watch(self, watches: List[Dict[SearchMatch, RepostWatch]], repost: Post):
    repost_watch_notify(watches, self.reddit, self.response_handler, repost)
    with self.uowm.start() as uow:
        for w in watches:
            w['watch'].last_detection = func.utc_timestamp()
            uow.repostwatch.update(w['watch'])
            try:
                uow.commit()
            except Exception as e:
                log.exception('Failed to save repost watch %s', w['watch'].id, exc_info=True)