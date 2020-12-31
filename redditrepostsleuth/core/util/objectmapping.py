from typing import Dict

from praw.models import Submission
from datetime import datetime

from prawcore import Forbidden

from redditrepostsleuth.core.db.databasemodels import Post, RedditImagePost, RedditImagePostCurrent
from redditrepostsleuth.core.model.hashwrapper import HashWrapper
from redditrepostsleuth.core.model.search_results.image_post_search_match import ImagePostSearchMatch
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from redditrepostsleuth.core.model.search_results.link_post_search_match import LinkPostSearchMatch
from redditrepostsleuth.core.util.helpers import get_post_type_pushshift


def submission_to_post(submission: Submission, source: str = 'praw') -> Post:
    """
    Convert a PRAW Submission object into a Post object
    :param submission:
    """
    #log.debug('Converting submission %s to post', submission.id)
    post = Post()
    post.post_id = submission.id
    post.url = submission.url
    post.shortlink = submission.__dict__.get('shortlink', None)
    post.author = submission.author.name if submission.author else None
    post.created_at = datetime.utcfromtimestamp(submission.created_utc)
    post.subreddit = submission.subreddit.display_name
    post.title = submission.title
    post.perma_link = submission.permalink
    post.crosspost_parent = submission.__dict__.get('crosspost_parent', None)
    post.selftext = submission.__dict__.get('selftext', None)
    post.crosspost_checked = True
    post.ingested_from = source
    if submission.is_self:
        post.post_type = 'text'
    else:
        try:
            post.post_type = submission.__dict__.get('post_hint', None)
        except (AttributeError, Forbidden) as e:
            pass


    # TODO - Do this lookup at time of checking reposts.  It's slow and slows down ingest
    """
    try:
        post.crosspost_parent = submission.crosspost_parent
    except AttributeError as e:
        pass
    """

    return post

def pushshift_to_post(submission: Dict, source: str = 'pushshift') -> Post:
    post = Post()
    post.post_id = submission.get('id', None)
    post.url = submission.get('url', None)
    post.shortlink = submission.get('shortlink', None)
    post.author = submission.get('author', None)
    post.created_at = datetime.utcfromtimestamp(submission.get('created_utc', None))
    post.subreddit = submission.get('subreddit', None)
    post.title = submission.get('title', None)
    post.perma_link = submission.get('permalink', None)
    post.crosspost_parent = submission.get('crosspost_parent', None)
    post.selftext = submission.get('selftext', None)
    post.crosspost_checked = True
    post.ingested_from = source
    post.post_type = get_post_type_pushshift(submission)

    return post


def post_to_hashwrapper(post: Post):
    wrapper = HashWrapper()
    wrapper.post_id = post.post_id
    wrapper.image_hash = post.image_hash
    wrapper.created_at = post.created_at
    return wrapper

def hash_tuple_to_hashwrapper(hash_tup):
    wrapper = HashWrapper()
    wrapper.post_id = hash_tup[0]
    wrapper.image_hash = hash_tup[1]
    return wrapper

def annoy_result_to_image_search_match(result: Dict, orig_id: int) -> ImagePostSearchMatch:
    match = ImagePostSearchMatch()
    match.original_id = orig_id
    match.match_id = result['id']
    match.annoy_distance = result['distance']
    return match

def post_to_link_post_search_match(post: Post, orig_id: int) -> RepostMatch:
    match = LinkPostSearchMatch(post, post.id)
    match.post = post
    match.match_id = post.id
    match.original_id = orig_id
    return match

def post_to_image_post(post: Post) -> RedditImagePost:
    return RedditImagePost(
        dhash_h=post.dhash_h,
        dhash_v=post.dhash_v,
        post_id=post.post_id,
        created_at=post.created_at
    )

def post_to_image_post_current(post: Post) -> RedditImagePostCurrent:
    return RedditImagePostCurrent(
        dhash_h=post.dhash_h,
        dhash_v=post.dhash_v,
        post_id=post.post_id,
        created_at=post.created_at
    )