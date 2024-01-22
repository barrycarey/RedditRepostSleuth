import html
import json
import logging
import os
import sys
import time

import jwt
import redis
import requests
from praw import Reddit
from praw.exceptions import PRAWException
from prawcore import NotFound, Forbidden, Redirect
from sqlalchemy import text, func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import HttpProxy, StatsTopRepost, StatsTopReposter
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.constants import EXCLUDE_FROM_TOP_REPOSTERS
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod_praw, get_bot_permissions
from redditrepostsleuth.core.util.replytemplates import MONITORED_SUB_MOD_REMOVED_CONTENT, \
    MONITORED_SUB_MOD_REMOVED_SUBJECT

log = logging.getLogger(__name__)
log = get_configured_logger(__name__)
def update_proxies(uowm: UnitOfWorkManager) -> None:
    with uowm.start() as uow:
        auth_token = os.getenv('WEBSHARE_AUTH')
        if not auth_token:
            log.error('No WebShare auth token provided')
            return
        log.info('Requesting proxies from WebShare')
        res = requests.get(
            'https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100',
            headers={'Authorization': f'Token {auth_token}'}
        )

        if res.status_code != 200:
            log.error('Invalid status from WebShare API: %s', res.status_code)
            return
        res_data = json.loads(res.text)
        if not res_data['results']:
            log.error('No proxies received from API.  Aborting')
            return

        log.info('Deleting existing proxies')
        uow.http_proxy.delete_all()
        uow.commit()
        for proxy in res_data['results']:
            uow.http_proxy.add(
                HttpProxy(address=f'{proxy["proxy_address"]}:{proxy["port"]}', provider='WebShare')
            )
        uow.commit()

def update_top_reposts(uow: UnitOfWork, post_type_id: int, day_range: int = None):
    # reddit.info(reddit_ids_to_lookup):
    log.info('Getting top repostors for post type %s with range %s', post_type_id, day_range)
    range_query = "SELECT repost_of_id, COUNT(*) c FROM repost WHERE detected_at > NOW() - INTERVAL :days DAY AND post_type_id=:posttype GROUP BY repost_of_id HAVING c > 5 ORDER BY c DESC"
    all_time_query = "SELECT repost_of_id, COUNT(*) c FROM repost WHERE post_type_id=:posttype GROUP BY repost_of_id HAVING c > 5 ORDER BY c DESC"
    if day_range:
        query = range_query
        uow.session.execute(text('DELETE FROM stat_top_repost WHERE post_type_id=:posttype AND day_range=:days'),
                            {'posttype': post_type_id, 'days': day_range})
    else:
        query = all_time_query
        uow.session.execute(text('DELETE FROM stat_top_repost WHERE post_type_id=:posttype AND day_range IS NULL'),
                            {'posttype': post_type_id})

    uow.commit()



    result = uow.session.execute(text(query), {'posttype': post_type_id, 'days': day_range})
    for row in result:
        stat = StatsTopRepost()
        stat.post_id = row[0]
        stat.post_type_id = post_type_id
        stat.day_range = day_range
        stat.repost_count = row[1]
        stat.updated_at = func.utc_timestamp()
        stat.nsfw = False
        uow.stat_top_repost.add(stat)
        uow.commit()

def run_update_top_reposts(uow: UnitOfWork) -> None:
    post_types = [1, 2, 3]
    day_ranges = [1, 7, 14, 30, None]
    for post_type_id in post_types:
        for days in day_ranges:
            update_top_reposts(uow, post_type_id, days)

def update_top_reposters(uow: UnitOfWork, post_type_id: int, day_range: int = None) -> None:
    log.info('Getting top repostors for post type %s with range %s', post_type_id, day_range)
    range_query = "SELECT author, COUNT(*) c FROM repost WHERE detected_at > NOW() - INTERVAL :days DAY  AND post_type_id=:posttype AND author is not NULL AND author!= '[deleted]' GROUP BY author HAVING c > 10 ORDER BY c DESC"
    all_time_query = "SELECT author, COUNT(*) c FROM repost WHERE post_type_id=:posttype AND author is not NULL AND author!= '[deleted]' GROUP BY author HAVING c > 10 ORDER BY c DESC"
    if day_range:
        query = range_query
    else:
        query = all_time_query

    if day_range:
        uow.session.execute(text('DELETE FROM stat_top_reposters WHERE post_type_id=:posttype AND day_range=:days'),
                            {'posttype': post_type_id, 'days': day_range})
    else:
        uow.session.execute(text('DELETE FROM stat_top_reposters WHERE post_type_id=:posttype AND day_range IS NULL'),
                            {'posttype': post_type_id})
    uow.commit()
    result = uow.session.execute(text(query), {'posttype': post_type_id, 'days': day_range})
    for row in result:
        if row[0] in EXCLUDE_FROM_TOP_REPOSTERS:
            continue
        stat = StatsTopReposter()
        stat.author = row[0]
        stat.post_type_id = post_type_id
        stat.day_range = day_range
        stat.repost_count = row[1]
        stat.updated_at = func.utc_timestamp()
        uow.stat_top_reposter.add(stat)
        uow.commit()

def run_update_top_reposters(uow: UnitOfWork):
    post_types = [1, 2, 3]
    day_ranges = [1, 7, 14, 30, None]
    for post_type_id in post_types:
        for days in day_ranges:
            update_top_reposters(uow, post_type_id, days)


def token_checker() -> None:
    config = Config()
    redis_client = redis.Redis(host=config.redis_host, port=config.redis_port, db=config.redis_database,
                         password=config.redis_password, decode_responses=True)
    token = redis_client.get('prof_token')
    if token:
        r = requests.get(f'{config.util_api}/validate-token?token={token}')
        if r.status_code == 200:
            response = json.loads(r.text)
            if response['token_status'] == 'valid':
                log.info('Existing token is valid')
                return
        else:
            log.error('Problem validating existing token')

    token_res = requests.get(f'{config.util_api}/token')
    if token_res.status_code != 200:
        log.error('Failed to get new token')
        return
    #decoded_token = jwt.decode(json.loads(token_res.text), '', algorithms=["HS256"], options={"verify_signature": False})
    new_token = json.loads(token_res.text)
    redis_client.set('prof_token', new_token)
    log.info('New token set in Redis')

def update_monitored_sub_data(
        uow: UnitOfWork,
        subreddit_name: str,
        reddit: Reddit,
        notification_svc: NotificationService,
        response_handler: ResponseHandler
) -> None:
    monitored_sub = uow.monitored_sub.get_by_sub(subreddit_name)
    if not monitored_sub:
        log.error('Failed to find subreddit %s', subreddit_name)
        return
    subreddit = reddit.subreddit(monitored_sub.name)

    monitored_sub.is_mod = is_sub_mod_praw(monitored_sub.name, 'repostsleuthbot', reddit)

    if not monitored_sub.failed_admin_check_count:
        monitored_sub.failed_admin_check_count = 0

    if monitored_sub.is_mod:
        if monitored_sub.failed_admin_check_count > 0:
            notification_svc.send_notification(
                f'Failed admin check for [r/{monitored_sub.name}](https://reddit.com/r/{monitored_sub.name}) reset',
                subject='Failed Admin Check Reset'
            )
        monitored_sub.failed_admin_check_count = 0
        uow.commit()
    else:
        monitored_sub.failed_admin_check_count += 1
        monitored_sub.active = False
        uow.commit()
        notification_svc.send_notification(
            f'Failed admin check for [r/{monitored_sub.name}](https://reddit.com/r/{monitored_sub.name}) increased to {monitored_sub.failed_admin_check_count}.',
            subject='Failed Admin Check Increased'
        )


    if monitored_sub.failed_admin_check_count == 2:
        subreddit = reddit.subreddit(monitored_sub.name)
        message = MONITORED_SUB_MOD_REMOVED_CONTENT.format(hours='72', subreddit=monitored_sub.name)
        try:
            response_handler.send_mod_mail(
                subreddit.display_name,
                message,
                MONITORED_SUB_MOD_REMOVED_SUBJECT,
                source='mod_check'
            )
        except PRAWException:
            pass
        return
    elif monitored_sub.failed_admin_check_count >= 4 and monitored_sub.name.lower() != 'dankmemes':
        notification_svc.send_notification(
            f'[r/{monitored_sub.name}](https://reddit.com/r/{monitored_sub.name}) failed admin check {monitored_sub.failed_admin_check_count} times',
            subject='Removing Monitored Subreddit'
        )
        uow.monitored_sub.remove(monitored_sub)
        uow.commit()
        return
    elif monitored_sub.failed_admin_check_count > 0:
        log.info('Subreddit %s failed admin check, skipping remaining checks', monitored_sub.name)

    try:
        monitored_sub.subscribers = subreddit.subscribers
    except NotFound as e:
        log.warning('Subreddit %s has been banned.  Removing', monitored_sub.name)
        uow.monitored_sub.remove(monitored_sub)
        uow.commit()
        return
    except Redirect as e:
        log.exception('')

    monitored_sub.is_private = True if subreddit.subreddit_type == 'private' else False
    monitored_sub.nsfw = True if subreddit.over18 else False
    log.info('[Subscriber Update] %s: %s subscribers', monitored_sub.name, monitored_sub.subscribers)

    perms = get_bot_permissions(subreddit) if monitored_sub.is_mod else []
    monitored_sub.post_permission = True if 'all' in perms or 'posts' in perms else None
    monitored_sub.wiki_permission = True if 'all' in perms or 'wiki' in perms else None
    log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', monitored_sub.name, monitored_sub.post_permission,
             monitored_sub.wiki_permission)



    uow.commit()

if __name__ == '__main__':
    uowm = UnitOfWorkManager(get_db_engine(Config()))
    #update_proxies(uowm)
    #sys.exit()
    while True:
        token_checker()
        time.sleep(240)
