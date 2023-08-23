import json
import logging
from typing import Optional
from urllib.parse import urlparse

import requests
from sqlalchemy import func
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import UserReview
from redditrepostsleuth.core.exception import UtilApiException


log = logging.getLogger(__name__)

known_domains = [
        'instagram.com',
        'patreon.com',
        'tiktok.com',
        'twitter.com',
        'deviantart.com',
        'facebook.com',
        'reddit.com',
        'youtube.com'
    ]

landing_domains = [
    'beacons.ai',
    'linktr.ee',
    'linkbio.co',
    'snipfeed.co'
]

flagged_words = [
    'fans.ly',
    'onlyfans.com',
    'fansly.com'
]

def check_profile_links_for_landing_pages(profile_links: list[str]) -> Optional[str]:
    for link in profile_links:
        for domain in landing_domains:
            if domain in link:
                return link

def check_profile_links_for_flagged(profile_links: list[str]) -> Optional[str]:
    for link in profile_links:
        log.info(link)
        for domain in flagged_words:
            if domain in link:
                return domain


def check_page_source_for_flagged_words(page_source: str) -> str:
    for domain in flagged_words:
        if domain in page_source:
            return domain

def process_landing_link(url: str) -> Optional[str]:
    config = Config()
    url_to_fetch = f'{config.util_api}/page-source?url={url}'
    parsed_url = urlparse(url)
    all_urls = flagged_words + known_domains + landing_domains
    if parsed_url.netloc not in all_urls:
        log.error('---------------------------------------> %s', url)
    response = requests.get(url_to_fetch)
    if response.status_code != 200:
        log.warning('No page text return for %s', url)
        raise UtilApiException(f'Failed to fetch beacons page source.  URL {url}')

    return check_page_source_for_flagged_words(response.text)


def check_user(user: UserReview) -> UserReview:
    config = Config()
    url = f'{config.util_api}/profile?username={user.username}'
    try:
        response = requests.get(url)
    except ConnectionError:
        log.error('Util API not responding')
        raise UtilApiException(f'Util API failed to connect')
    except Exception:
        log.exception('Unexpected exception from Util API')
        raise

    if response.status_code != 200:
        log.warning('Non 200 return code %s from Util API')
        raise UtilApiException(f'Unexpected status {response.status_code} from util API')

    profile_links = json.loads(response.text)
    user.last_checked = func.utc_timestamp()

    content_links_found = check_profile_links_for_flagged(profile_links)
    if content_links_found:
        log.info('User %s: Found flagged link %s', user.username, content_links_found)
        user.content_links_found = True
        user.notes = f'Profile links match {content_links_found}'
        return user

    landing_link_found = check_profile_links_for_landing_pages(profile_links)
    if landing_link_found:
        landing_link_with_flagged_content = process_landing_link(landing_link_found)
        if landing_link_with_flagged_content:
            user.content_links_found = True
            user.notes = f'Landing link with flagged urls: {landing_link_with_flagged_content}'
            if len(user.notes) > 150:
                user.notes = user.notes[0:149]

    user.last_checked = func.utc_timestamp()
    return user

if __name__ == '__main__':
    user = UserReview(username='AbandonedJoint')
    check_user(user)