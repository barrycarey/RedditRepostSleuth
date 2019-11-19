from datetime import datetime
from typing import Text

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.repostmatch import RepostMatch


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

def hamming_distance_filter(target_hamming_distance: float):
    def hamming_filter(match: ImageMatch):
        if match.annoy_distance <= target_hamming_distance:
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