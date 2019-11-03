from typing import List

from praw import Reddit
from praw.models import Submission

from redditrepostsleuth.common.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.core.db.databasemodels import Post

from redditrepostsleuth.common.model.repostmatch import RepostMatch
from redditrepostsleuth.common.model.repostwrapper import RepostWrapper


# TODO: Should be able to safely remove this now


from redditrepostsleuth.common.util.objectmapping import post_to_repost_match


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


def clean_repost_matches(repost: RepostWrapper) -> List[RepostMatch]:
    """
    Take a list of reposts, remove any cross posts and deleted posts
    :param posts: List of posts
    """
    #repost.matches = filter_matching_images(repost.matches, repost.checked_post)
    matches = [match for match in repost.matches if not match.post.crosspost_parent and match.post.created_at < repost.checked_post.created_at]
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
    # TODO - Strip this out
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

def verify_oc(submission: Submission, repost_service) -> bool:
    """
    Check a provided post to see if it is OC
    :param submission: Submission to check
    :param repost_service: Repost processing service
    :return: boolean
    """
    log.info('Checking submission %s is OC', submission.id)
    result = repost_service.find_all_occurrences(submission)
    matches = [match for match in result.matches if not match.post.crosspost_parent]
    if matches:
        log.info('Submission %s is not OC.  Found %s matches', submission.id, len(matches))
        return False
    else:
        log.info('Submission %s is OC', submission.id)
        return True

def check_link_repost(post: Post, uowm: UnitOfWorkManager) -> RepostWrapper:
    with uowm.start() as uow:
        repost = RepostWrapper()
        repost.checked_post = post
        repost.matches = [post_to_repost_match(match, post.id) for match in uow.posts.find_all_by_url_hash(post.url_hash) if
                          match.post_id != post.post_id]
        repost.matches = clean_repost_matches(repost)

    return repost