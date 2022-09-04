from datetime import datetime

from praw.models import Submission
from prawcore import Forbidden

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.util.helpers import get_post_type_pushshift, get_post_type_id


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

    return post

def pushshift_to_post(submission: dict) -> Post:
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
    post.post_type = get_post_type_pushshift(submission)
    post.post_type_int = get_post_type_id(post.post_type)
    post.nsfw = submission.get('over_18', None)

    return post

