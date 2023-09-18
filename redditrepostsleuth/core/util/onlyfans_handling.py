import json
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from praw import Reddit
from requests import Response
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import UserReview
from redditrepostsleuth.core.exception import UtilApiException, UserNotFound

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

config = Config()

@dataclass
class LinkCheckResult:
    source: str
    url: str

    def __repr__(self):
        return f'{self.source} links match {self.url}'

def check_links_for_landing_pages(links: list[str]) -> Optional[str]:
    """
    Take a list of links and see if any match the landing domains we have flagged
    :param links: links to check
    :return: The matching URL if one is found, else None
    """
    for link in links:
        for domain in landing_domains:
            if domain in link:
                return link

def check_links_for_flagged_domains(links: list[str]) -> Optional[str]:
    """
    Check a list of links and see if any domains are on our flagged list
    :param links: list of links to check
    :return: flagged domain or None
    """
    for link in links:
        for domain in flagged_words:
            if domain in link:
                return domain


def check_page_source_for_flagged_words(page_source: str) -> str:
    """
    Take the HTML source of a page and see if it contains any of our flagged domains
    :param page_source: HTML source
    :return: flagged domain or None
    """
    for domain in flagged_words:
        if domain in page_source:
            return domain

def process_landing_link(url: str) -> Optional[str]:

    url_to_fetch = f'{config.util_api}/page-source?url={url}'
    parsed_url = urlparse(url)
    all_urls = flagged_words + known_domains + landing_domains
    if parsed_url.netloc not in all_urls:
        # So we can flag landing domains we're not checking
        log.error('---------------------------------------> %s', url)
    response = requests.get(url_to_fetch)
    if response.status_code != 200:
        log.warning('No page text return for %s', url)
        raise UtilApiException(f'Failed to fetch beacons page source.  URL {url}')

    return check_page_source_for_flagged_words(response.text)


def fetch_from_util_api(url: str) -> Response:
    try:
        response = requests.get(url)
    except ConnectionError:
        log.error('Util API not responding')
        raise UtilApiException(f'Util API failed to connect')
    except Exception:
        log.exception('Unexpected exception from Util API')
        raise

    return response

def get_profile_links(username: str) -> list[str]:
    url = f'{config.util_api}/profile?username={username}'
    response = fetch_from_util_api(url)

    if response.status_code != 200:
        log.warning('Non 200 return code %s from Util API')
        raise UtilApiException(f'Unexpected status {response.status_code} from util API')

    profile_links = json.loads(response.text)
    return profile_links

def check_user_for_promoter_links(username: str) -> Optional[LinkCheckResult]:

    profile_links = get_profile_links(username)

    content_links_found = check_links_for_flagged_domains(profile_links)
    if content_links_found:
        return LinkCheckResult(source='Profile', url=content_links_found)

    landing_link_found = check_links_for_landing_pages(profile_links)
    if landing_link_found:
        landing_link_with_flagged_content = process_landing_link(landing_link_found)
        if landing_link_with_flagged_content:
            return LinkCheckResult(source='Profile landing', url=landing_link_with_flagged_content)

    comment_links = get_links_from_comments(username)

    content_links_found = check_links_for_flagged_domains(comment_links)
    if content_links_found:
        return LinkCheckResult(source='Comment', url=content_links_found)

    landing_link_found = check_links_for_landing_pages(comment_links)
    if landing_link_found:
        landing_link_with_flagged_content = process_landing_link(landing_link_found)
        if landing_link_with_flagged_content:
            return LinkCheckResult(source='Comment landing', url=landing_link_with_flagged_content)

def get_links_from_comments(username: str) -> list[str]:
    url = f'{config.util_api}/reddit/user-comment?username={username}'
    response = fetch_from_util_api(url)

    if response.status_code == 404:
        raise UserNotFound(f'User {username} does not exist or is banned')

    if response.status_code != 200:
        log.warning('Unexpected status %s from util API', response.status_code)
        raise UtilApiException(f'Unexpected status {response.status_code} from util API')

    response_json = json.loads(response.text)
    all_urls = []

    for comment in response_json['data']['children']:
        all_urls += re.findall(r'href=[\'"]?([^\'" >]+)', comment['data']['body_html'])

    log.debug('User %s has %s comment links', username, len(all_urls))

    return list(set(all_urls))

def get_links_from_comments_praw(username: str, reddit: Reddit) -> list[str]:
    all_urls = []
    redditor = reddit.redditor(username)
    if not redditor:
        log.warning('Failed to find Redditor with username %s', username)
        return all_urls

    for comment in redditor.comments.new(limit=100):
        all_urls += re.findall(r'href=[\'"]?([^\'" >]+)', comment.body_html)

    log.debug('User %s has %s comment links', username, len(all_urls))

    return list(set(all_urls))

if __name__ == '__main__':
    user = UserReview(username='AbandonedJoint')
    check_user(user)