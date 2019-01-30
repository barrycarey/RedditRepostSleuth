from praw.models import Submission
from datetime import datetime
from redditrepostsleuth.model.db.databasemodels import Post


def submission_to_post(submission: Submission) -> Post:
    """
    Convert a PRAW Submission object into a Post object
    :param submission:
    """
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
        if hasattr(submission, 'post_hint'):
            post.post_type = submission.post_hint
        else:
            print('Missing Post Hint')
    if hasattr(submission, 'crosspost_parent'):
        post.crosspost_parent = submission.crosspost_parent


    return post
