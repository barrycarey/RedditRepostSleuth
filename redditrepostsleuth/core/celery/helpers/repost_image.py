from typing import List, NoReturn

from redditrepostsleuth.core.exception import IngestHighMatchMeme
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.db.databasemodels import Post, ImageRepost, InvestigatePost
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper

from redditrepostsleuth.core.model.repostwrapper import RepostWrapper
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.util.helpers import create_meme_template
from redditrepostsleuth.core.util.repost_filters import filter_dead_urls


def check_for_high_match_meme(search_results: ImageRepostWrapper, uowm: UnitOfWorkManager) -> NoReturn:
    if search_results.meme_template is not None:
        return

    with uowm.start() as uow:
        meme_template = None
        if len(search_results.matches) > 5 and search_results.checked_post.subreddit.lower() == 'memes':
            try:
                meme_template = create_meme_template(search_results.checked_post.url, search_results.checked_post.title)
                meme_template.approved = False
                meme_template.created_from_submission = f'https://redd.it/{search_results.checked_post.post_id}'
                uow.meme_template.add(meme_template)
            except Exception as e:
                log.exception('Failed to create meme templaet', exc_info=True)

        elif len(search_results.matches) > 10 and 'meme' in search_results.checked_post.subreddit.lower():
            try:
                meme_template = create_meme_template(search_results.checked_post.url, search_results.checked_post.title)
                meme_template.approved = False
                meme_template.created_from_submission = f'https://redd.it/{search_results.checked_post.post_id}'
                uow.meme_template.add(meme_template)
            except Exception as e:
                log.exception('Failed to create meme template', exc_info=True)

        if meme_template:
            uow.commit()
            log.info('Saved new meme template for post %s in %s', search_results.checked_post.post_id, search_results.checked_post.subreddit)
            # Raise exception so celery will retry the task and use the new meme template
            raise IngestHighMatchMeme('Created meme template.  Post needs to be rechecked')

def find_matching_images(post: Post, dup_service: DuplicateImageService) -> ImageRepostWrapper:
    """
    Take a given post and dup image service and return all matches
    :param post: Reddit Post
    :param dup_service: Dup Image Service
    :return: RepostWrapper
    """
    result = dup_service.check_duplicates_wrapped(post, filter_dead_matches=False, meme_filter=True, source='ingest_repost')
    log.debug('Found %s matching images', len(result.matches))
    return result

def save_image_repost_result(search_results: RepostWrapper, uowm: UnitOfWorkManager) -> None:
    """
    Take a found repost and save to the database
    :param search_results:
    :param uowm:
    :return:
    """
    # TODO - This whole function needs to be broken up
    with uowm.start() as uow:

        search_results.checked_post.checked_repost = True
        if not search_results.matches:
            log.debug('Post %s has no matches', search_results.checked_post.post_id)
            uow.posts.update(search_results.checked_post)
            uow.commit()
            return

        if len(search_results.matches) > 0:
            check_for_high_match_meme(search_results, uowm) # This intentionally throws if we create a meme template
            final_matches = search_results.matches
            log.debug('Checked Image (%s): %s', search_results.checked_post.created_at, search_results.checked_post.url)
            for match in final_matches:
                log.debug('Matching Image: %s (%s) (Hamming: %s - Annoy: %s): %s', match.post.post_id,
                          match.post.created_at, match.hamming_distance, match.annoy_distance, match.post.url)
            repost_of = get_oldest_active_match(search_results.matches)
            if not repost_of:
                log.info('No active matches, not saving report')
                return

            log.info('Creating repost. Post %s is a repost of %s', search_results.checked_post.url, repost_of.post.url)

            new_repost = ImageRepost(post_id=search_results.checked_post.post_id,
                                     repost_of=repost_of.post.post_id,
                                     hamming_distance=repost_of.hamming_distance,
                                     annoy_distance=repost_of.annoy_distance)
            repost_of.post.repost_count += 1
            uow.posts.update(repost_of.post)
            uow.image_repost.add(new_repost)
            search_results.matches = final_matches

        uow.posts.update(search_results.checked_post)
        uow.commit()

def get_oldest_active_match(matches: List[ImageMatch]) -> ImageMatch:
    """
    Take a list of ImageMatches and return the oldest match that is still alive
    :rtype: ImageMatch
    :param matches: List of matches
    :return: ImageMatch
    """
    for match in matches:
        if filter_dead_urls(match):
            return match
