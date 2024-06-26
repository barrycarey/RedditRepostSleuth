import os
from datetime import datetime
from time import perf_counter
from typing import NoReturn

import pymysql
from celery import Task
from prawcore import TooManyRequests
from requests.exceptions import ConnectionError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AdminTask
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, Post, UserReview
from redditrepostsleuth.core.exception import UtilApiException, UserNotFound
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import log, configure_logger
from redditrepostsleuth.core.util.helpers import chunk_list
from redditrepostsleuth.core.util.onlyfans_handling import check_user_for_promoter_links, \
    check_user_comments_for_promoter_links

log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post_ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[ContextFilter()]
)


class PyMysqlTask(Task):
    def __init__(self):
        self.config = Config()

    def get_conn(self):
        return pymysql.connect(host=self.config.db_host,
                        user=self.config.db_user,
                        password=self.config.db_password,
                        db=self.config.db_name,
                        cursorclass=pymysql.cursors.SSDictCursor)

def get_conn():
    return pymysql.connect(host=os.getenv('DB_HOST'),
                           user=os.getenv('DB_USER'),
                           password=os.getenv('DB_PASSWORD'),
                           db=os.getenv('DB_NAME'),
                           cursorclass=pymysql.cursors.SSDictCursor)

def cleanup_post(post_id: str, uowm) -> None:
    try:
        with uowm.start() as uow:
            uow.posts.remove_by_post_id(post_id)
            uow.image_post.remove_by_post_id(post_id)
            uow.investigate_post.remove_by_post_id(post_id)
            #uow.image_repost.remove_by_post_id(post_id)
            uow.bot_comment.remove_by_post_id(post_id)
            uow.summons.remove_by_post_id(post_id)
            uow.image_search.remove_by_post_id(post_id)
            uow.user_report.remove_by_post_id(post_id)
            uow.repostwatch.remove_by_post_id(post_id)
            uow.commit()
            log.info('Deleted post %s', post_id)
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=PyMysqlTask)
def bulk_delete(self, post_ids: list[str]):
    if not post_ids:
        return
    db_conn = self.get_conn()
    try:
        log.debug('Deleting Batch')
        in_params = ','.join(['%s'] * len(post_ids))
        queries = [
            'DELETE FROM reddit_post where post_id IN (%s)' % in_params,
            'DELETE FROM reddit_image_post WHERE post_id in (%s)' % in_params,
            'DELETE FROM investigate_post WHERE post_id in (%s)' % in_params,
            'DELETE FROM reddit_bot_comment WHERE post_id in (%s)' % in_params,
            'DELETE FROM reddit_bot_summons WHERE post_id in (%s)' % in_params,
            'DELETE FROM reddit_image_search WHERE post_id in (%s)' % in_params,
            'DELETE FROM reddit_user_report WHERE post_id in (%s)' % in_params,
            'DELETE FROM reddit_repost_watch WHERE post_id in (%s)' % in_params,
        ]

        with db_conn.cursor() as cur:
            for q in queries:
                res = cur.execute(q, post_ids)
            db_conn.commit()
    except Exception as e:
        log.exception('')
    finally:
        db_conn.close()

@celery.task(bind=True, base=AdminTask)
def delete_post_task(self, post_id: str) -> None:
    cleanup_post(post_id, self.uowm)

def update_last_delete_check(ids: list[int], uowm) -> None:
    with uowm.start() as uow:
        batch = []
        for id in ids:
            batch.append({'id': id, 'last_deleted_check': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})
        uow.session.bulk_update_mappings(Post, batch)
        uow.commit()

@celery.task(bind=True, base=AdminTask)
def update_last_deleted_check(self, post_ids: list[int]) -> None:
    try:
        log.info('Updating last deleted check timestamp for %s posts', len(post_ids))
        start = perf_counter()
        update_last_delete_check(post_ids, self.uowm)
        print(f'Save Time: {round(perf_counter() - start, 5)}')
    except Exception as e:
        log.exception()


@celery.task(bind=True, base=AdminTask)
def update_subreddit_config_from_database(self, monitored_sub: MonitoredSub, user_data: dict) -> NoReturn:
    try:
        self.config_updater.update_wiki_config_from_database(monitored_sub, notify=False)
    except Exception as e:
        log.exception('')
    self.config_updater.notification_svc.send_notification(
        f'[r/{monitored_sub.name}](https://reddit.com/r/{monitored_sub.name}) config updated on site by [u/{user_data["name"]}](https://reddit.com/u/{user_data["name"]})',
        subject='Config updated on repostsleuth.com'
    )


@celery.task(bind=True, base=AdminTask, autoretry_for=(UtilApiException,ConnectionError,TooManyRequests), retry_kwards={'max_retries': 3, 'retry_backoff': True})
def check_user_for_only_fans(self, username: str) -> None:
    skip_names = ['[deleted]', 'AutoModerator']

    if username in skip_names:
        log.info('Skipping name %s', username)
        return

    try:
        with self.uowm.start() as uow:
            user = uow.user_review.get_by_username(username)

            if user:
                delta = datetime.utcnow() - user.last_checked
                if delta.days < 30:
                    log.info('Skipping existing user %s, last check was %s days ago', username, delta.days)
                    return
                user.content_links_found = False
                user.notes = None
                user.last_checked = func.utc_timestamp()

            log.info('Checking user %s', username)
            if not user:
                user = UserReview(username=username)
            try:
                result = check_user_for_promoter_links(username)
            except UserNotFound as e:
                log.warning(e)
                return

            if result:
                log.info('Promoter found: %s - %s', username, str(result))
                user.content_links_found = True
                user.notes = str(result)
            uow.user_review.add(user)
            uow.commit()
    except (UtilApiException, ConnectionError, TooManyRequests) as e:
        raise e
    except IntegrityError:
        pass
    except Exception as e:
        log.exception('')


@celery.task(bind=True, base=AdminTask, autoretry_for=(UtilApiException,ConnectionError,TooManyRequests), retry_kwards={'max_retries': 3})
def check_user_comments_for_only_fans(self, username: str) -> None:
    """
    This should be run after the profile check so we don't do any timeframe checking
    :param self:
    :param username:
    :return:
    """
    skip_names = ['[deleted]', 'AutoModerator']

    if username in skip_names:
        log.info('Skipping name %s', username)
        return

    try:
        with self.uowm.start() as uow:
            user = uow.user_review.get_by_username(username)

            if not user:
                log.error('User not found: %s', username)

            try:
                result = check_user_comments_for_promoter_links(username)
            except UserNotFound as e:
                log.warning(e)
                return

            if result:
                log.info('Promoter found: %s - %s', username, str(result))
                user.content_links_found = True
                user.notes = str(result)
            uow.user_review.add(user)
            uow.commit()
    except (UtilApiException, ConnectionError, TooManyRequests) as e:
        raise e
    except IntegrityError:
        pass
    except Exception as e:
        log.exception('')


