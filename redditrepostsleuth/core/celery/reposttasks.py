from typing import NoReturn

import requests
from redlock import RedLockError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from requests.exceptions import ConnectTimeout

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AnnoyTask, RedditTask, RepostTask
from redditrepostsleuth.core.celery.task_logic.repost_image import save_image_repost_result, \
    repost_watch_notify, check_for_post_watch
from redditrepostsleuth.core.db.databasemodels import Post, RepostWatch, Repost
from redditrepostsleuth.core.exception import NoIndexException, IngestHighMatchMeme
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import log, configure_logger
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.util.helpers import get_default_link_search_settings, get_default_image_search_settings
from redditrepostsleuth.core.util.repost_helpers import get_link_reposts, filter_search_results, log_search

log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post_ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[ContextFilter()]
)


@celery.task(bind=True, base=AnnoyTask, serializer='pickle', ignore_results=True, autoretry_for=(RedLockError, NoIndexException, IngestHighMatchMeme), retry_kwargs={'max_retries': 20, 'countdown': 300})
def check_image_repost_save(self, post: Post) -> NoReturn:

    try:
        r = requests.head(post.url)
        if r.status_code != 200:
            log.info('Skipping image that is deleted %s', post.url)
            celery.send_task('redditrepostsleuth.core.celery.admin_tasks.delete_post_task', args=[post.post_id])
            return

        search_settings = get_default_image_search_settings(self.config)
        search_settings.max_matches = 75
        search_results = self.dup_service.check_image(
            post.url,
            post=post,
            search_settings=search_settings,
            source='ingest'
        )

        save_image_repost_result(search_results, self.uowm, source='ingest', high_match_check=True)

        if search_results.matches:
            watches = check_for_post_watch(search_results.matches, self.uowm)
            if watches and self.config.enable_repost_watch:
                notify_watch.apply_async((watches, post), queue='watch_notify')

    except (RedLockError, NoIndexException, IngestHighMatchMeme):
        raise
    except (ConnectTimeout):
        log.warning('Failed to validate image url at %s', post.url)
    except Exception as e:
        log.exception('')


@celery.task(bind=True, base=RepostTask, ignore_results=True, serializer='pickle')
def link_repost_check(self, posts, ):
    try:
        with self.uowm.start() as uow:
            for post in posts:

                try:
                    log.debug('Checking URL for repost: %s', post.url_hash)
                    search_results = get_link_reposts(post.url, self.uowm,
                                                      get_default_link_search_settings(self.config),
                                                      post=post)

                    if len(search_results.matches) > 10000:
                        log.info('Link hash %s shared %s times. Search time was %s', post.url_hash,
                                 len(search_results.matches), search_results.search_times.total_search_time)

                    search_results = filter_search_results(
                        search_results,
                        uitl_api=f'{self.config.util_api}/maintenance/removed'
                    )
                    search_results.search_times.stop_timer('total_search_time')
                    log.info('Link Query Time: %s', search_results.search_times.query_time)
                    log_search(self.uowm, search_results, 'ingest', 'link')
                    if not search_results.matches:
                        log.debug('Not matching links for post %s', post.post_id)
                        uow.commit()
                        continue

                    log.info('Found %s matching links', len(search_results.matches))
                    log.info('Creating Link Repost. Post %s is a repost of %s', post.post_id,
                             search_results.matches[0].post.post_id)
                    repost_of = search_results.matches[0].post

                    new_repost = Repost(
                        post_id=post.id,
                        repost_of_id=repost_of.id,
                        author=post.author,
                        source='ingest',
                        subreddit=post.subreddit,
                        search_id=search_results.logged_search.id,
                        post_type_id=post.post_type_id
                    )
                    uow.repost.add(new_repost)

                    try:
                        uow.commit()
                    except IntegrityError as e:
                        uow.rollback()
                        log.exception('Error saving link repost', exc_info=True)

                except Exception as e:
                    log.exception('')

    except Exception as e:
        log.exception('')


@celery.task(bind=True, base=RedditTask, ignore_results=True)
def notify_watch(self, watches: list[dict[SearchMatch, RepostWatch]], repost: Post):
    repost_watch_notify(watches, self.reddit, self.response_handler, repost)
    with self.uowm.start() as uow:
        for w in watches:
            w['watch'].last_detection = func.utc_timestamp()
            uow.repostwatch.update(w['watch'])
            try:
                uow.commit()
            except Exception as e:
                log.exception('Failed to save repost watch %s', w['watch'].id, exc_info=True)