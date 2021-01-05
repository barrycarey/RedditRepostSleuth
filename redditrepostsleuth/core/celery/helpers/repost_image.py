from typing import List, NoReturn, Dict, Text

from redditrepostsleuth.core.db.databasemodels import Post, ImageRepost, RepostWatch, MemeTemplate
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import IngestHighMatchMeme
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.replytemplates import WATCH_NOTIFY_OF_MATCH
from redditrepostsleuth.core.util.repost_filters import filter_dead_urls


def check_for_high_match_meme(search_results: ImageSearchResults, uowm: UnitOfWorkManager) -> NoReturn:
    if search_results.meme_template is not None:
        return

    with uowm.start() as uow:
        meme_template = None
        if len(search_results.matches) > 5 and 'meme' in search_results.checked_post.subreddit.lower():
            try:
                meme_hashes = get_image_hashes(search_results.checked_post.url, hash_size=32)
            except Exception as e:
                log.error('Failed to get meme hash for %s', search_results.checked_post.post_id)
                return

            try:
                meme_template = MemeTemplate(
                    dhash_h=search_results.checked_post.dhash_h,
                    dhash_256=meme_hashes['dhash_h'],
                    post_id=search_results.checked_post.post_id
                )

                uow.meme_template.add(meme_template)
                uow.commit()
            except Exception as e:
                log.exception('Failed to create meme template', exc_info=True)
                meme_template = None

        if meme_template:
            log.info('Saved new meme template for post %s in %s', search_results.checked_post.post_id, search_results.checked_post.subreddit)
            # Raise exception so celery will retry the task and use the new meme template
            raise IngestHighMatchMeme('Created meme template.  Post needs to be rechecked')


def save_image_repost_result(search_results: ImageSearchResults, uowm: UnitOfWorkManager) -> None:
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
                                     annoy_distance=repost_of.annoy_distance,
                                     author=search_results.checked_post.author,
                                     search_id=search_results.search_id,
                                     subreddit=search_results.checked_post.subreddit)
            repost_of.post.repost_count += 1
            uow.posts.update(repost_of.post)
            uow.image_repost.add(new_repost)
            search_results.matches = final_matches

        uow.posts.update(search_results.checked_post)
        uow.commit()

def save_image_repost_general(search_results: ImageSearchResults, uowm: UnitOfWorkManager, source: Text) -> None:
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
                                     annoy_distance=repost_of.annoy_distance,
                                     author=search_results.checked_post.author,
                                     search_id=search_results.search_id,
                                     subreddit=search_results.checked_post.subreddit,
                                     source=source
                                     )

            uow.image_repost.add(new_repost)
            search_results.matches = final_matches

        uow.posts.update(search_results.checked_post)
        uow.commit()


def get_oldest_active_match(matches: List[SearchMatch]) -> SearchMatch:
    """
    Take a list of ImageMatches and return the oldest match that is still alive
    :rtype: SearchMatch
    :param matches: List of matches
    :return: ImageMatch
    """
    for match in matches:
        if filter_dead_urls(match):
            return match

def check_for_post_watch(matches: List[SearchMatch], uowm: UnitOfWorkManager) -> List[Dict]:
    results = []
    with uowm.start() as uow:
        for match in matches:
            watches = uow.repostwatch.get_all_active_by_post_id(match.post.post_id)
            if watches:
                log.info('Found %s active watch requests for post %s', len(watches), match.post.post_id)
                for watch in watches:
                    results.append({'match': match, 'watch': watch})
    return results

def repost_watch_notify(watches: List[Dict[SearchMatch, RepostWatch]], reddit: RedditManager, response_handler: ResponseHandler, repost: Post):
    for watch in watches:
        # TODO - What happens if we don't get redditor back?
        redditor = reddit.redditor(watch['watch'].user)
        msg = WATCH_NOTIFY_OF_MATCH.format(
            watch_shortlink=f"https://redd.it/{watch['watch'].post_id}",
            repost_shortlink=f"https://redd.it/{repost.post_id}",
            percent_match=watch['match'].hamming_match_percent
        )
        log.info('Sending repost watch PM to %s', redditor.name)
        response_handler.send_private_message(
            redditor,
            msg,
            subject='A post you are watching has been reposted',
            source='watch',
            post_id=watch['watch'].post_id
        )