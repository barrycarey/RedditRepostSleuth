import json

import requests
from typing import Dict, List

import imagehash

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.util.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import ImageConversioinException
from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.core.util.imagehashing import generate_img_by_url
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance

def post_type_from_url(url: str) -> str:
    """
    Try to guess post type based off URL
    :param url:
    """
    image_exts = ['.jpg', '.png', '.jpeg', '.gif']
    for ext in image_exts:
        if ext in url.lower():
            return 'image'

def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

def get_post_type_pushshift(submission: Dict) -> str:
    # TODO - Go over this whole function
    if submission.get('is_self', None):
        return 'text'

    post_hint = submission.get('post_hint', None)
    if post_hint:
        return post_hint

    image_exts = ['.jpg', '.png', '.jpeg', '.gif']
    for ext in image_exts:
        if ext in submission['url']:
            #log.debug('Post URL %s is an image', submission['url'])
            return 'image'

    reddit = get_reddit_instance(config=Config())
    is_video = submission.get('is_video', None)
    if is_video:
        #log.debug('Post %s has is_video value of %s. It is a video', submission['id'], is_video)
        # Since the push push obj didn't have a post hint, we need to query reddit
        print('Hitting Reddit API')
        reddit_sub = reddit.submission(id=submission['id'])
        post_hint = reddit_sub.__dict__.get('post_hint', None)
        if post_hint:
            #log.debug('Returning post hintg %s for post %s', post_hint, reddit_sub.id)
            return post_hint
        else:
            #log.debug('Unable to determine video type for post %s', reddit_sub.id)
            return 'video'

    # Last ditch to get post_hint
    reddit_sub = reddit.submission(id=submission['id'])
    return reddit_sub.__dict__.get('post_hint', None)

def searched_post_str(post: Post, count: int) -> str:
    output = '**Searched'
    if post.post_type == 'image':
        output = output + f' Images:** {count:,}'
    elif post.post_type == 'link':
        output = output + f' Links:** {count:,}'
    else:
        output = output + f':** {count:,}'

    return output

def create_first_seen(post: Post, subreddit: str, first_last: str = 'First') -> str:
    """
    Create a first seen string to use in a comment.  Takes into account subs that dont' allow links
    :param post: DB Post obj
    :return: final string
    """
    if subreddit and subreddit in NO_LINK_SUBREDDITS:
        seen = f"First seen in {post.subreddit} on {post.created_at.strftime('%Y-%m-%d')}"
    else:
        seen = f"{first_last} seen [Here](https://redd.it/{post.post_id}) on {post.created_at.strftime('%Y-%m-%d')}"

    return seen

def create_meme_template(url: str, name: str = None, target_hamming=9, target_annoy=0) -> MemeTemplate:
    """
    Take a given URL and create a meme template from it
    :param url: URL to create template from
    :param name: Name of template
    :return: MemeTemplate
    """
    try:
        img = generate_img_by_url(url)
    except ImageConversioinException as e:
        raise

    dhash_h = imagehash.dhash(img, hash_size=16)
    dhash_v = imagehash.dhash_vertical(img, hash_size=16)
    ahash = imagehash.average_hash(img, hash_size=16)

    return MemeTemplate(
        dhash_h=str(dhash_h),
        dhash_v=str(dhash_v),
        ahash=str(ahash),
        name=name,
        example=url,
        template_detection_hamming=10,
        target_annoy=target_annoy,
        target_hamming=target_hamming
    )


def build_markdown_list(matches: List[ImageMatch]) -> str:
    result = ''
    for match in matches:
        result += f'* {match.post.created_at.strftime("%d-%m-%Y")} - [https://redd.it/{match.post.post_id}](https://redd.it/{match.post.post_id}) [{match.post.subreddit}] [{(100 - match.hamming_distance) / 100:.2%} match]\n'
    return result

def build_image_msg_values_from_search(search_results: ImageRepostWrapper, uowm: UnitOfWorkManager = None, **kwargs) -> Dict:
    results_values = {}
    base_values = {
        'closest_sub': search_results.closest_match.post.subreddit,
        'target_match_percent': f'{search_results.target_match_percent}%',
        'closest_url': search_results.closest_match.post.url,
        'closest_shortlink': f'https://redd.it/{search_results.closest_match.post.post_id}',
        'closest_percent_match': f'{search_results.closest_match.hamming_match_percent}%',
        'closest_created_at': search_results.closest_match.post.created_at,
    }
    if search_results.matches:
        results_values = {
            'newest_percent_match': f'{search_results.matches[-1].hamming_match_percent}%',
            'oldest_percent_match': f'{search_results.matches[0].hamming_match_percent}%',
            'match_list': build_markdown_list(search_results.matches),
            'meme_template_id': search_results.meme_template.id if search_results.meme_template else None,
            'false_positive_data': json.dumps(
                {
                    'post': f'https://redd.it/{search_results.checked_post.post_id}',
                    'meme_template': search_results.meme_template.id if search_results.meme_template else None
                }
            ),
        }

    return {**results_values, **base_values, **kwargs}


def build_msg_values_from_search(search_results: ImageRepostWrapper, uowm: UnitOfWorkManager = None, **kwargs) -> Dict:
    """
    Take a ImageRepostWrapper object and return a dict of values for use in a message template
    :param search_results: ImageRepostWrapper
    :param uowm: UnitOfWorkManager
    """
    base_values = {
        'total_searched': f'{search_results.total_searched:,}',
        'search_time': search_results.total_search_time,
        'total_posts': 0,
        'match_count': len(search_results.matches),
        'post_type': search_results.checked_post.post_type,
        'this_subreddit': search_results.checked_post.subreddit,
        'times_word': 'times' if len(search_results.matches) > 1 else 'time',
        'stats_searched_post_str': searched_post_str(search_results.checked_post, search_results.total_searched),
        'post_shortlink': f'https://redd.it/{search_results.checked_post.post_id}'
    }

    results_values = {}

    if search_results.matches:
        results_values = {
            'oldest_created_at': search_results.matches[0].post.created_at,
            'oldest_url': search_results.matches[0].post.url,
            'oldest_shortlink': f'https://redd.it/{search_results.matches[0].post.post_id}',
            'oldest_sub': search_results.matches[0].post.subreddit,
            'newest_created_at': search_results.matches[-1].post.created_at,
            'newest_url': search_results.matches[-1].post.url,
            'newest_shortlink': f'https://redd.it/{search_results.matches[-1].post.post_id}',
            'newest_sub': search_results.matches[-1].post.subreddit,
            'first_seen': create_first_seen(search_results.matches[0].post, search_results.checked_post.subreddit),
            'last_seen': create_first_seen(search_results.matches[-1].post, search_results.checked_post.subreddit, 'Last'),

        }

    if uowm:
        with uowm.start() as uow:
            base_values['total_posts'] = f'{uow.posts.get_newest_post().id:,}'

    return {**base_values, **results_values, **kwargs}
