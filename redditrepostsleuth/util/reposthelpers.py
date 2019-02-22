from typing import List

from praw import Reddit

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.model.repostmatch import RepostMatch
from redditrepostsleuth.model.repostwrapper import RepostWrapper
from redditrepostsleuth.model.imagematch import ImageMatch

# TODO: Should be able to safely remove this now
from redditrepostsleuth.util.helpers import get_reddit_instance


def filter_matching_images(raw_list: List[RepostMatch], post_being_checked: Post) -> List[Post]:
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


def clean_repost_matches(matches: List[RepostMatch]) -> List[RepostMatch]:
    """
    Take a list of reposts, remove any cross posts and deleted posts
    :param posts: List of posts
    """
    #repost.matches = filter_matching_images(repost.matches, repost.checked_post)
    matches = [match for match in matches if not match.post.crosspost_parent]
    matches = sort_reposts(matches)
    return matches


def sort_reposts(posts: List[RepostMatch], reverse=False) -> List[RepostMatch]:
    """
    Take a list of reposts and sort them by date
    :param posts:
    """
    return sorted(posts, key=lambda x: x.post.created_at, reverse=reverse)

def remove_newer_posts(posts: List[Post], repost_check: Post):
    return [post for post in posts if post.created_at < repost_check.created_at]


def check_for_image_crosspost(matches: List[ImageMatch], reddit: Reddit = None) -> List[ImageMatch]:
    if not reddit:
        reddit = get_reddit_instance()
    for match in matches:
        if match.post.crosspost_checked:
            continue
        match.post.crosspost_parent = get_crosspost_parent(match.post, reddit)
        match.post.crosspost_checked = True
    return matches

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

def set_shortlink(post: Post) -> Post:
    """
    Take a post and set its short link if it doesn't exist
    :param post:
    :return:
    """
    if not post.shortlink:
        reddit = get_reddit_instance()
        try:
            post.shortlink = reddit.submission(post.post_id).shortlink
        except Exception as e:
            # TODO: Specific exception
            log.error('Failed to set shortlink for post %s. Exception type: %s', post.post_id, type(e))

    return post

def get_crosspost_parent_batch(ids: List[str], reddit: Reddit):
    submissions = reddit.info(fullnames=ids)
    result = []
    for submission in submissions:
        result.append({
            'id': submission.id,
            'crosspost_Parent': submission.__dict__.get('crosspost_parent', None)
        })
    log.info('Crosspost Parent Results: %s', result)
    return result