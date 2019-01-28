from praw.models import Submission

from redditrepostsleuth.db.model.post import Post


def praw_post_to_model(submission: Submission) -> Post:
    """
    Convert a PRAW Submission object into a Post object
    :param submission:
    """
    post = Post(
        url=submission.url,
        post_type=submission.post_hint,
        author=submission.author.name,
        created_at=submission.created,
        id=submission.id,

    )
