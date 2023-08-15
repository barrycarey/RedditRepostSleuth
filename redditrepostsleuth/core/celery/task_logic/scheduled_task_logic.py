import html
import json
import logging
import os
import time

import jwt
import redis
import requests
from sqlalchemy import text, func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import HttpProxy, StatsTopRepost, StatsTopReposters
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger

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

def update_top_reposts(uowm: UnitOfWorkManager):
    # reddit.info(reddit_ids_to_lookup):
    post_types = [2, 3]
    day_ranges = [1, 7, 14, 30, 365, None]
    range_query = "SELECT repost_of_id, COUNT(*) c FROM repost WHERE detected_at > NOW() - INTERVAL :days DAY AND post_type_id=:posttype GROUP BY repost_of_id HAVING c > 5 ORDER BY c DESC"
    all_time_query = "SELECT repost_of_id, COUNT(*) c FROM repost WHERE post_type_id=:posttype GROUP BY repost_of_id HAVING c > 5 ORDER BY c DESC"
    with uowm.start() as uow:
        for post_type in post_types:
            for days in day_ranges:
                log.info('Getting top reposts for post type %s with range %s', post_type, days)
                if days:
                    query = range_query
                else:
                    query = all_time_query
                uow.session.execute(
                    text('DELETE FROM stat_top_repost WHERE post_type_id=:posttype AND day_range=:days'),
                    {'posttype': post_type, 'days': days})
                uow.commit()
                result = uow.session.execute(text(query), {'posttype': post_type, 'days': days})
                for row in result:
                    stat = StatsTopRepost()
                    stat.post_id = row[0]
                    stat.post_type_id = post_type
                    stat.day_range = days
                    stat.repost_count = row[1]
                    stat.updated_at = func.utc_timestamp()
                    stat.nsfw = False
                    uow.stat_top_repost.add(stat)
                    uow.commit()

def update_top_reposters(uowm: UnitOfWorkManager):
    post_types = [2, 3]
    day_ranges = [1, 7, 14, 30, None]
    range_query = "SELECT author, COUNT(*) c FROM repost WHERE detected_at > NOW() - INTERVAL :days DAY  AND post_type_id=:posttype AND author is not NULL AND author!= '[deleted]' GROUP BY author HAVING c > 5 ORDER BY c DESC"
    all_time_query = "SELECT author, COUNT(*) c FROM repost WHERE post_type_id=:posttype AND author is not NULL AND author!= '[deleted]' GROUP BY author HAVING c > 5 ORDER BY c DESC"
    with uowm.start() as uow:
        for post_type in post_types:
            for days in day_ranges:
                log.info('Getting top repostors for post type %s with range %s', post_type, days)
                if days:
                    query = range_query
                else:
                    query = all_time_query
                uow.session.execute(text('DELETE FROM stat_top_reposters WHERE post_type_id=:posttype AND day_range=:days'), {'posttype': post_type, 'days': days})
                uow.commit()
                result = uow.session.execute(text(query), {'posttype': post_type, 'days': days})
                for row in result:
                    stat = StatsTopReposters()
                    stat.author = row[0]
                    stat.post_type_id = post_type
                    stat.day_range = days
                    stat.repost_count = row[1]
                    stat.updated_at = func.utc_timestamp()
                    uow.stat_top_reposter.add(stat)
                    uow.commit()


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
    decoded_token = jwt.decode(json.loads(token_res.text), '', algorithms=["HS256"], options={"verify_signature": False})
    redis_client.set('prof_token', decoded_token['sub'])
    log.info('New token set in Redis')


if __name__ == '__main__':

    while True:
        token_checker()
        time.sleep(240)
