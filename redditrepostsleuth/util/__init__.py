from praw.models import Submission
from datetime import datetime

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Post


def submission_to_post(submission: Submission) -> Post:
    """
    Convert a PRAW Submission object into a Post object
    :param submission:
    """
    log.debug('Converting submission %s to post', submission.id)
    post = Post()
    post.post_id = submission.id
    post.url = submission.url
    post.author = submission.author.name if submission.author else None
    post.created_at = datetime.fromtimestamp(submission.created)
    post.subreddit = submission.subreddit.display_name
    post.title = submission.title
    post.perma_link = submission.permalink
    if submission.is_self:
        post.post_type = 'text'
    else:
        try:
            post.post_type = submission.post_hint
        except AttributeError as e:
            print('Missing Post Hint')

    # TODO - Do this lookup at time of checking reposts.  It's slow and slows down ingest
    """
    try:
        post.crosspost_parent = submission.crosspost_parent
    except AttributeError as e:
        pass

    """

    return post

