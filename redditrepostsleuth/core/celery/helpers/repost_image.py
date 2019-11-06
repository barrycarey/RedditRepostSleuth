from typing import List

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.db.databasemodels import Post, ImageRepost, InvestigatePost
from redditrepostsleuth.core.model.imagematch import ImageMatch

from redditrepostsleuth.core.model.repostwrapper import RepostWrapper
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.util.helpers import is_image_still_available


# TODO - Drop logging lines

def find_matching_images(post: Post, dup_service: DuplicateImageService) -> RepostWrapper:
    """
    Take a given post and dup image service and return all matches
    :param post: Reddit Post
    :param dup_service: Dup Image Service
    :return: RepostWrapper
    """
    result = dup_service.check_duplicates_wrapped(post, filter_dead_matches=False)
    log.debug('Found %s matching images', len(result.matches))
    return result

def save_image_repost_result(repost: RepostWrapper, uowm: UnitOfWorkManager) -> None:
    """
    Take a found repost and save to the database
    :param repost:
    :param uowm:
    :return:
    """
    with uowm.start() as uow:

        repost.checked_post.checked_repost = True
        if not repost.matches:
            log.debug('Post %s has no matches', repost.checked_post.post_id)
            uow.posts.update(repost.checked_post)
            uow.commit()
            return

        if len(repost.matches) > 0:
            final_matches = repost.matches
            log.debug('Checked Image (%s): %s', repost.checked_post.created_at, repost.checked_post.url)
            for match in final_matches:
                log.debug('Matching Image: %s (%s) (Hamming: %s - Annoy: %s): %s', match.post.post_id,
                          match.post.created_at, match.hamming_distance, match.annoy_distance, match.post.url)
            repost_of = get_oldest_active_match(repost.matches)
            if not repost_of:
                log.info('No active matches, not saving report')
                return

            log.info('Creating repost. Post %s is a repost of %s', repost.checked_post.url, repost_of.post.url)

            new_repost = ImageRepost(post_id=repost.checked_post.post_id,
                                     repost_of=repost_of.post.post_id,
                                     hamming_distance=repost_of.hamming_distance,
                                     annoy_distance=repost_of.annoy_distance)
            repost_of.post.repost_count += 1
            uow.posts.update(repost_of.post)
            uow.repost.add(new_repost)
            repost.matches = final_matches

            if len(repost.matches) > 20:
                log.info('Adding Investigate Post')
                inv_post = InvestigatePost(post_id=repost_of.post.post_id, matches=len(repost.matches), url=repost.checked_post.url)
                uow.investigate_post.add(inv_post)

        uow.posts.update(repost.checked_post)
        uow.commit()

def get_oldest_active_match(matches: List[ImageMatch]) -> ImageMatch:
    """
    Take a list of ImageMatches and return the oldest match that is still alive
    :rtype: ImageMatch
    :param matches: List of matches
    :return: ImageMatch
    """
    for match in matches:
        if is_image_still_available(match.post.url):
            return match
