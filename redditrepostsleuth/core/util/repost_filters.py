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