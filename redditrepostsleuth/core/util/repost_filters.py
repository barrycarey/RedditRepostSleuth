import json
from datetime import datetime
from typing import Text, List
import random

import requests
from praw import Reddit
from requests.exceptions import SSLError, ConnectionError, ReadTimeout

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from redditrepostsleuth.core.util.constants import USER_AGENTS


def cross_post_filter(match: RepostMatch) -> bool:
    if match.post.crosspost_parent:
        log.debug('Crosspost Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
        return False
    else:
        return True


def same_sub_filter(subreddit: Text):
    def sub_filter(match):
        if match.post.subreddit != subreddit:
            log.debug('Same Sub Reject: Orig sub: %s - Match Sub: %s - %s', subreddit, match.post.subreddit,
                      f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return sub_filter


def annoy_distance_filter(target_annoy_distance: float):
    def annoy_filter(match: ImageMatch):
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
    def hamming_filter(match: ImageMatch):
        if match.hamming_distance <= target_hamming_distance:
            return True
        log.debug('Hamming Filter Reject - Target: %s Actual: %s - %s', target_hamming_distance,
                  match.hamming_distance, f'https://redd.it/{match.post.post_id}')
        return False
    return hamming_filter


def filter_newer_matches(cutoff_date: datetime):
    def date_filter(match: RepostMatch):
        if match.post.created_at >= cutoff_date:
            log.debug('Date Filter Reject: Target: %s Actual: %s - %s', cutoff_date.strftime('%Y-%d-%m %H:%M:%S'),
                      match.post.created_at.strftime('%Y-%d-%m %H:%M:%S'), f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return date_filter

def filter_title_distance(threshold: int):
    def title_filter(match: RepostMatch):
        if match.title_similarity <= threshold:
            log.debug('Title Similarity Filter Reject: Target: %s Actual: %s', threshold, match.title_similarity)
            return False
        return True
    return title_filter

def filter_days_old_matches(cutoff_days: int):
    def days_filter(match: RepostMatch):
        if (datetime.utcnow() - match.post.created_at).days > cutoff_days:
            log.debug('Date Cutoff Reject: Target: %s Actual: %s - %s', cutoff_days,
                      (datetime.utcnow() - match.post.created_at).days, f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return days_filter


def filter_same_author(author: Text):
    def filter_author(match: RepostMatch):
        if author == match.post.author:
            log.debug('Author Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return filter_author


def filter_same_post(post_id: Text):
    def same_post(match: RepostMatch):
        if match.post.post_id == post_id:
            log.debug('Same Post Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
            return False
        return True
    return same_post

def filter_title_keywords(keywords: List[Text]):
    def filter_title(match: RepostMatch):
        for kw in keywords:
            log.info('Title: %s - KW: %s', match.post.title, kw)
            if kw in match.post.title.lower():
                log.debug('Title Filter Reject. Title contains %s', kw)
                return False
        return True
    return filter_title

def filter_no_dhash(match: ImageMatch):
    if not match.post.dhash_h:
        log.debug('Dhash Filter Reject - %s', f'https://redd.it/{match.post.post_id}')
        return False
    return True

def filter_dead_urls(match: ImageMatch):
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

def filter_removed_posts(reddit: Reddit, matches: List[RepostMatch]):
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

def filter_dead_urls_remote(util_api: Text, reddit: Reddit, matches: List[RepostMatch]):
    match_urls = [{'id': match.post.post_id, 'url': match.post.url} for match in matches]
    try:
        res = requests.post(util_api, json=match_urls)
    except ConnectionError:
        log.error('Problem reaching retail API, doing local check')
        return filter_removed_posts(reddit, matches)
    except Exception as e:
        log.exception('Problem reaching retail API, doing local check', exc_info=True)
        return filter_removed_posts(reddit, matches)

    if res.status_code != 200:
        log.error('Non 200 status from util api (%s), doing local dead URL check', res.status_code)
        return filter_removed_posts(reddit, matches)
    res_data = json.loads(res.text)
    removed_matches = [match['id'] for match in res_data if match['action'] == 'remove']
    for removed_id in removed_matches:
        del matches[next(i for i, x in enumerate(matches) if x.post.post_id == removed_id)]
    return matches