import os
from datetime import datetime
from time import perf_counter
from typing import NoReturn, Dict, Text, List

import pymysql
from praw.exceptions import PRAWException
from sqlalchemy import func

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AdminTask, RedditTask, SqlAlchemyTask, PyMysqlTask
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, RepostWatch, Post
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import log, configure_logger
from redditrepostsleuth.core.util.helpers import batch_check_urls
from redditrepostsleuth.core.util.reddithelpers import get_subscribers, is_sub_mod_praw, get_bot_permissions
from redditrepostsleuth.core.util.replytemplates import MONITORED_SUB_MOD_REMOVED_CONTENT, \
    MONITORED_SUB_MOD_REMOVED_SUBJECT

log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post_ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[ContextFilter()]
)

config = Config()

def get_conn():
    return pymysql.connect(host=os.getenv('DB_HOST'),
                           user=os.getenv('DB_USER'),
                           password=os.getenv('DB_PASSWORD'),
                           db=os.getenv('DB_NAME'),
                           cursorclass=pymysql.cursors.SSDictCursor)

def bulk_delete_old(post_ids: list[str]):
    if not post_ids:
        return
    conn = get_conn()
    in_params = ','.join(['%s'] * len(post_ids))
    queries = [
        'DELETE FROM reddit_post where post_id IN (%s)' % in_params,
        'DELETE FROM reddit_image_post WHERE post_id in (%s)'  % in_params,
        'DELETE FROM investigate_post WHERE post_id in (%s)' % in_params,
        'DELETE FROM reddit_bot_comment WHERE post_id in (%s)' % in_params,
        'DELETE FROM reddit_bot_summons WHERE post_id in (%s)' % in_params,
        'DELETE FROM reddit_image_search WHERE post_id in (%s)' % in_params,
        'DELETE FROM reddit_user_report WHERE post_id in (%s)' % in_params,
        'DELETE FROM reddit_repost_watch WHERE post_id in (%s)' % in_params,
        ]

    with conn.cursor() as cur:
        for q in queries:
            res = cur.execute(q, post_ids)
        conn.commit()

    log.info('Deleted Batch')

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
                log.info(q)
                res = cur.execute(q, post_ids)
                print(res)
            db_conn.commit()
    except Exception as e:
        log.exception('')
    finally:
        db_conn.close()

@celery.task(bind=True, base=SqlAlchemyTask)
def delete_post_task(self, post_id: str) -> None:
    cleanup_post(post_id, self.uowm)

def post_to_dict(post: Post):
    print('')
    return {
        'id': post.id,
        'last_deleted_check': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),

    }

def update_last_delete_check(ids: list[int], uowm) -> None:
    with uowm.start() as uow:
        batch = []
        for id in ids:
            batch.append({'id': id, 'last_deleted_check': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})
        uow.session.bulk_update_mappings(Post, batch)
        uow.commit()
@celery.task(bind=True, base=SqlAlchemyTask)
def update_last_deleted_check(self, post_ids: list[int]) -> None:
    try:
        log.info('Updating last deleted check timestamp for %s posts', len(post_ids))
        start = perf_counter()
        update_last_delete_check(post_ids, self.uowm)
        print(f'Save Time: {round(perf_counter() - start, 5)}')
    except Exception as e:
        log.exception()

@celery.task(bind=True, base=SqlAlchemyTask)
def update_last_deleted_check_old(self, post_ids: list[str]) -> None:
    with self.uowm.start() as uow:
        posts = uow.posts.get_all_by_post_ids(post_ids)
        log.info('Updating last deleted check timestamp for %s posts', len(posts))
        start = perf_counter()
        for post in posts:
            post.last_deleted_check = func.utc_timestamp()
        uow.commit()
        print(f'Save Time: {round(perf_counter() - start, 5)}')

@celery.task(bind=True, base=AdminTask)
def check_for_subreddit_config_update_task(self, monitored_sub: MonitoredSub) -> NoReturn:
    self.config_updater.check_for_config_update(monitored_sub, notify_missing_keys=False)

@celery.task(bind=True, base=AdminTask)
def update_subreddit_config_from_database(self, monitored_sub: MonitoredSub, user_data: Dict) -> NoReturn:
    self.config_updater.update_wiki_config_from_database(monitored_sub, notify=True)
    self.config_updater.notification_svc.send_notification(
        f'r/{monitored_sub.name} config updated on site by {user_data["name"]}',
        subject='**Config updated on repostsleuth.com**'
    )


@celery.task(bind=True, base=RedditTask)
def update_monitored_sub_stats(self, sub_name: Text) -> NoReturn:
    with self.uowm.start() as uow:
        monitored_sub: MonitoredSub = uow.monitored_sub.get_by_sub(sub_name)
        if not monitored_sub:
            log.error('Failed to find subreddit %s', sub_name)
            return

        monitored_sub.subscribers = get_subscribers(monitored_sub.name, self.reddit.reddit)

        log.info('[Subscriber Update] %s: %s subscribers', monitored_sub.name, monitored_sub.subscribers)
        monitored_sub.is_mod = is_sub_mod_praw(monitored_sub.name, 'repostsleuthbot', self.reddit.reddit)
        perms = get_bot_permissions(monitored_sub.name, self.reddit) if monitored_sub.is_mod else []
        monitored_sub.post_permission = True if 'all' in perms or 'posts' in perms else None
        monitored_sub.wiki_permission = True if 'all' in perms or 'wiki' in perms else None
        log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', monitored_sub.name, monitored_sub.post_permission, monitored_sub.wiki_permission)

        if not monitored_sub.failed_admin_check_count:
            monitored_sub.failed_admin_check_count = 0

        if monitored_sub.is_mod:
            if monitored_sub.failed_admin_check_count > 0:
                self.notification_svc.send_notification(
                    f'Failed admin check for r/{monitored_sub.name} reset',
                    subject='Failed Admin Check Reset'
                )
            monitored_sub.failed_admin_check_count = 0
        else:
            monitored_sub.failed_admin_check_count += 1
            self.notification_svc.send_notification(
                f'Failed admin check for r/{monitored_sub.name} increased to {monitored_sub.failed_admin_check_count}.',
                subject='Failed Admin Check Increased'
            )

        if monitored_sub.failed_admin_check_count == 2:
            subreddit = self.reddit.subreddit(monitored_sub.name)
            message = MONITORED_SUB_MOD_REMOVED_CONTENT.format(hours='72', subreddit=monitored_sub.name)
            try:
                subreddit.message(
                    MONITORED_SUB_MOD_REMOVED_SUBJECT,
                    message
                )
            except PRAWException:
                pass
        elif monitored_sub.failed_admin_check_count >= 4 and monitored_sub.name.lower() != 'dankmemes':
            self.notification_svc.send_notification(
                f'Sub r/{monitored_sub.name} failed admin check 4 times.  Removing',
                subject='Removing Monitored Subreddit'
            )
            uow.monitored_sub.remove(monitored_sub)

        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def check_if_watched_post_is_active(self, watches: List[RepostWatch]):
    urls_to_check = []
    with self.uowm.start() as uow:
        for watch in watches:
            post = uow.posts.get_by_post_id(watch.post_id)
            if not post:
                continue
            urls_to_check.append({'url': post.url, 'id': str(watch.id)})

        active_urls = batch_check_urls(
            urls_to_check,
            f'{self.config.util_api}/maintenance/removed'
        )

    for watch in watches:
        if not next((x for x in active_urls if x['id'] == str(watch.id)), None):
            log.info('Removing watch %s', watch.id)
            uow.repostwatch.remove(watch)

    uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def save_image_index_map(self, map_data):
    pass