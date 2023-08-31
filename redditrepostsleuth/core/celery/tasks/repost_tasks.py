from typing import NoReturn

import requests
from redlock import RedLockError
from requests.exceptions import ConnectTimeout
from sqlalchemy import func

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AnnoyTask, RedditTask, RepostTask
from redditrepostsleuth.core.celery.task_logic.repost_image import repost_watch_notify, check_for_post_watch
from redditrepostsleuth.core.db.databasemodels import Post, RepostWatch
from redditrepostsleuth.core.exception import NoIndexException, IngestHighMatchMeme, IndexApiException
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import log, configure_logger
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.util.helpers import get_default_link_search_settings, get_default_image_search_settings, \
    get_default_text_search_settings
from redditrepostsleuth.core.util.repost.repost_helpers import filter_search_results
from redditrepostsleuth.core.util.repost.repost_search import text_search_by_post, image_search_by_post, \
    link_search

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
        with self.uowm.start() as uow:
            search_results = image_search_by_post(
                post,
                uow,
                self.dup_service,
                search_settings,
                'ingest',
                high_match_meme_check=True
            )

            if search_results.matches:
                watches = check_for_post_watch(search_results.matches, uow)
                if watches and self.config.enable_repost_watch:
                    notify_watch.apply_async((watches, post), queue='watch_notify')

    except (RedLockError, NoIndexException, IngestHighMatchMeme):
        raise
    except (ConnectTimeout):
        log.warning('Failed to validate image url at %s', post.url)
    except Exception as e:
        log.exception('')


@celery.task(bind=True, base=RepostTask, ignore_results=True, serializer='pickle')
def link_repost_check(self, post):

    try:
        with self.uowm.start() as uow:

            log.debug('Checking URL for repost: %s', post.url)
            search_results = link_search(post.url, uow,
                                         get_default_link_search_settings(self.config),
                                         'ingest',
                                         post=post,
                                         filter_function=filter_search_results
                                         )

            search_results.search_times.stop_timer('total_search_time')
            log.info('Link Query Time: %s', search_results.search_times.query_time)



    except Exception as e:
        log.exception('')


@celery.task(bind=True, base=RepostTask, ignore_results=True, serializer='pickle')
def check_for_text_repost_task(self, post: Post) -> None:
    log.debug('Checking post for repost: %s', post.post_id)
    try:
        with self.uowm.start() as uow:
            search_results = text_search_by_post(
                post,
                uow,
                get_default_text_search_settings(self.config),
                filter_function=filter_search_results,
                source='ingest'
            )
            log.info('Found %s matching text posts', len(search_results.matches))
    except IndexApiException as e:
        log.warning(e, exc_info=False)
        raise
    except Exception as e:
        log.exception('Unknown exception during test repost check')


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