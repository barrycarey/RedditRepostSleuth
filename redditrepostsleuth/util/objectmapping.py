from typing import Tuple

from praw.models import Submission
from datetime import datetime

from prawcore import Forbidden

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.model.hashwrapper import HashWrapper
from redditrepostsleuth.model.postdto import PostDto
from redditrepostsleuth.service.imagematch import ImageMatch


def submission_to_post(submission: Submission) -> Post:
    """
    Convert a PRAW Submission object into a Post object
    :param submission:
    """
    #log.debug('Converting submission %s to post', submission.id)
    post = Post()
    post.post_id = submission.id
    post.url = submission.url
    post.shortlink = submission.shortlink
    post.author = submission.author.name if submission.author else None
    post.created_at = datetime.fromtimestamp(submission.created_utc)
    post.subreddit = submission.subreddit.display_name
    post.title = submission.title
    post.perma_link = submission.permalink
    if submission.is_self:
        post.post_type = 'text'
    else:
        try:
            post.post_type = submission.post_hint
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

def submission_to_postdto(submission: Submission):
    postdto = PostDto()

    postdto.post_id = submission.id
    postdto.url = submission.url
    postdto.perma_link = submission.permalink
    postdto.author = submission.author.name if submission.author else None
    postdto.created_at = submission.created
    postdto.subreddit = submission.subreddit.display_name
    postdto.title = submission.title
    if submission.is_self:
        postdto.post_type = 'text'
    else:
        try:
            postdto.post_type = submission.post_hint
        except (AttributeError, Forbidden) as e:
            print('Missing Post Hint')

    return postdto


def postdto_to_post(postdto: PostDto):
    post = Post()
    post.id = postdto.id
    post.post_id = postdto.post_id
    post.url = postdto.url
    post.perma_link = postdto.perma_link
    post.post_type = postdto.post_type
    post.author = postdto.author
    post.created_at = postdto.created_at
    post.ingested_at = postdto.ingested_at if postdto.ingested_at else None
    post.subreddit = postdto.subreddit
    post.title = postdto.title
    post.crosspost_parent = postdto.crosspost_parent
    post.repost_of = postdto.repost_of
    post.image_hash = postdto.image_hash
    post.checked_repost = postdto.checked_repost
    post.crosspost_checked = postdto.crosspost_checked
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

def annoy_result_to_image_match(result: Tuple[int, float], orig_id: int) -> ImageMatch:
    match = ImageMatch()
    match.original_id = orig_id
    match.match_id = result[0]
    match.annoy_distance = result[1]
    return match