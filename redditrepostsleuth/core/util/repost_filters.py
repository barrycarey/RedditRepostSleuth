import json
import logging
from datetime import datetime
from typing import Text, List
import random

import requests
from praw import Reddit
from requests.exceptions import SSLError, ConnectionError, ReadTimeout

from redditrepostsleuth.core.util.utils import build_reddit_query_string
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.util.constants import USER_AGENTS, REDDIT_REMOVAL_REASONS
from redditrepostsleuth.core.util.helpers import batch_check_urls, chunk_list

log = logging.getLogger(__name__)


def cross_post_filter(match: SearchMatch) -> bool:
    if match.post.crosspost_parent:
        log.debug('Crosspost Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
        return False
    else:
        return True


def same_sub_filter(subreddit: Text):
    def sub_filter(match: SearchMatch):
        if match.post.subreddit != subreddit:
            log.debug('Same Sub Reject: Orig sub: %s - Match Sub: %s - %s', subreddit, match.post.subreddit,
                      f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return sub_filter


def annoy_distance_filter(target_annoy_distance: float):
    def annoy_filter(match: ImageSearchMatch):
        if match.annoy_distance <= target_annoy_distance:
            return True
        log.debug('Annoy Filter Reject - Target: %s Actual: %s - %s', target_annoy_distance, match.annoy_distance,
                  f'https://redd.it/{match.post.post_id}')
        return False
    return annoy_filter


def raw_annoy_filter(target_annoy_distance: float):
    def annoy_filter(item):
        return item[1] < target_annoy_distance
    return annoy_filter


def hamming_distance_filter(target_hamming_distance: float):
    def hamming_filter(match: ImageSearchMatch):
        if match.hamming_distance <= target_hamming_distance:
            return True
        log.debug('Hamming Filter Reject - Target: %s Actual: %s - %s', target_hamming_distance,
                  match.hamming_distance, f'https://redd.it/{match.post.post_id}')
        return False
    return hamming_filter


def filter_newer_matches(cutoff_date: datetime):
    def date_filter(match: SearchMatch):
        if match.post.created_at >= cutoff_date:
            log.debug('Date Filter Reject: Target: %s Actual: %s - %s', cutoff_date.strftime('%Y-%d-%m %H:%M:%S'),
                      match.post.created_at.strftime('%Y-%d-%m %H:%M:%S'), f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return date_filter


def filter_title_distance(threshold: int):
    def title_filter(match: SearchMatch):
        if match.title_similarity <= threshold:
            log.debug('Title Similarity Filter Reject: Target: %s Actual: %s', threshold, match.title_similarity)
            return False
        return True
    return title_filter


def filter_days_old_matches(cutoff_days: int):
    def days_filter(match: SearchMatch):
        if (datetime.utcnow() - match.post.created_at).days > cutoff_days:
            log.debug('Date Cutoff Reject: Target: %s Actual: %s - %s', cutoff_days,
                      (datetime.utcnow() - match.post.created_at).days, f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return days_filter


def filter_same_author(author: Text):
    def filter_author(match: SearchMatch):
        if author == match.post.author:
            log.debug('Author Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return filter_author


def filter_same_post(post_id: Text):
    def same_post(match: SearchMatch):
        if match.post.post_id == post_id:
            log.debug('Same Post Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return same_post


def filter_title_keywords(keywords: List[Text]):
    def filter_title(match: SearchMatch):
        for kw in keywords:
            log.info('Title: %s - KW: %s', match.post.title, kw)
            if kw in match.post.title.lower():
                log.debug('Title Filter Reject. Title contains %s', kw)
                return False
        return True
    return filter_title


def filter_no_dhash(match: ImageSearchMatch):
    if not match.post.hash_1:
        log.debug('Dhash Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
        return False
    return True


def filter_dead_urls(match: SearchMatch) -> bool:
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        r = requests.head(match.post.url, timeout=3, headers=headers)
    except (ConnectionError, SSLError, ReadTimeout):
        return False
    if r.status_code == 200:
        return True
    else:
        log.debug('Active URL Reject:  https://redd.it/%s', match.post.post_id)
        return False


def filter_removed_posts(reddit: Reddit, matches: List[SearchMatch]) -> List[SearchMatch]:
    """
    Take a list of SearchMatches, get the submission from Reddit and see if they have been removed
    :param reddit: Praw Reddit instance
    :param matches: List of matches
    :return: List of filtered matches
    """
    if not matches:
        return matches
    if len(matches) > 100:
        log.info('Skipping removed post check due to > 100 matches (%s)', len(matches))
        return matches
    post_ids = [f't3_{match.post.post_id}' for match in matches]
    submissions = reddit.info(post_ids)
    for sub in submissions:
        if sub.__dict__.get('removed', None):
            log.debug('Removed Post Filter Reject - %s', sub.id)
            del matches[next(i for i, x in enumerate(matches) if x.post.post_id == sub.id)]
    return matches


def filter_dead_urls_remote(util_api: Text, matches: List[SearchMatch]) -> List[SearchMatch]:
    """
    Batch checking a list of matches to see if the associated links have been removed.
    This function is using our utility API that runs on a Pool of VMs so we can check matches at high volume

    We are piggy backing the util API I use to clean deleted posts from the database.

    API response is:
    [
        {'id': '12345', 'action': 'remove'

    ]

    Several actions can be returned.  However, we're only interested in the remove since that results from the post's
    URL returning a 404

    :param util_api: API URL to call to get results
    :param matches: List of matches
    :return: List of filtered matches
    """
    results = []
    match_urls = [{'id': match.post.post_id, 'url': match.post.url} for match in matches]
    alive_urls = batch_check_urls(match_urls, util_api)
    for url in alive_urls:
        match = next((x for x in matches if x.post.post_id == url['id']), None)
        if match:
            results.append(match)
    return results


def filter_removed_posts_util_api(util_api: str, matches: List[SearchMatch]) -> List[SearchMatch]:
    results = []
    log.debug('Starting filter remove post with %s matches', len(matches))
    for chunk in chunk_list(matches, 100):
        url = f'{util_api}/reddit/info?submission_ids={build_reddit_query_string([p.post.post_id for p in chunk])}'
        try:
            response = requests.get(url)
            if response.status_code != 200:
                log.error('Bad status %s from util API.  Skipping check on this batch', response.status_code)
                results += chunk
                continue
        except Exception as e:
            log.exception('Problem reaching util API')
            results += chunk
            continue

        res_data = json.loads(response.text)
        for post in res_data['data']['children']:
            if post['data']['removed_by_category'] in REDDIT_REMOVAL_REASONS:
                continue
            match_to_keep = next((m for m in chunk if m.post.post_id == post['data']['id']), None)
            results.append(match_to_keep)

    log.debug('Finished filter removed posts with %s results', len(results))
    return results