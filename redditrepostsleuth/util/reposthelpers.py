from typing import List

from praw import Reddit

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.service.imagematch import ImageMatch

# TODO: Should be able to safely remove this now
def filter_matching_images(raw_list: List[ImageMatch], post_being_checked: Post) -> List[Post]:
    """
    Take a raw list if matched images.  Filter one ones meeting the following criteria.
        Same Author as post being checked - Gets rid of people posting to multiple subreddits
        If it has a crosspost parent - A cross post isn't considered a respost
        Same post ID as post being checked - The image list will contain the original image being checked
    :param raw_list: List of all matches
    :param post_being_checked: The posts we're checking is a repost
    """
    # TODO - Clean this up
    return [x for x in raw_list if x.post.crosspost_parent is None and post_being_checked.author != x.author]


def clean_reposts(repost: ImageRepostWrapper, reddit: Reddit = None) -> ImageRepostWrapper:
    """
    Take a list of reposts, remove any cross posts and deleted posts
    :param posts: List of posts
    """
    #repost.matches = filter_matching_images(repost.matches, repost.checked_post)
    repost.matches = sort_reposts(repost.matches)
    return repost


def sort_reposts(posts: List[ImageMatch], reverse=False) -> List[ImageMatch]:
    """
    Take a list of reposts and sort them by date
    :param posts:
    """
    return sorted(posts, key=lambda x: x.post.created_at, reverse=reverse)

def remove_newer_posts(posts: List[Post], repost_check: Post):
    return [post for post in posts if post.created_at < repost_check.created_at]

def get_crosspost_parent(post: Post, reddit: Reddit):
    submission = reddit.submission(id=post.post_id)
    if submission:
        try:
            result = submission.crosspost_parent
            log.debug('Post %s has corsspost parent %s', post.post_id, result)
            return result
        except AttributeError:
            log.debug('No crosspost parent for post %s', post.post_id)
            return None
    log.error('Failed to find submission with ID %s', post.post_id)