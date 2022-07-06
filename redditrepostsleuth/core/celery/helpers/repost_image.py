from typing import List, NoReturn, Dict, Text

from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.db.databasemodels import Post, RepostWatch, MemeTemplate, Repost
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import IngestHighMatchMeme
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.replytemplates import WATCH_NOTIFY_OF_MATCH


def check_for_high_match_meme(search_results: ImageSearchResults, uowm: UnitOfWorkManager) -> NoReturn:
    if search_results.meme_template is not None:
        return

    with uowm.start() as uow:
        meme_template = None
        # TODO - 1/12/2021 - Should probably remember the meme in subreddit check and generate more templates
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
                    post_id=search_results.checked_post.id
                )

                uow.meme_template.add(meme_template)
                uow.commit()
            except IntegrityError as e:
                log.exception(f'Failed to create meme template. Template already exists for post {search_results.checked_post.post_id}', exc_info=True)
                meme_template = None

        if meme_template:
            log.info('Saved new meme template for post %s in %s', search_results.checked_post.post_id, search_results.checked_post.subreddit)
            # Raise exception so celery will retry the task and use the new meme template
            raise IngestHighMatchMeme('Created meme template.  Post needs to be rechecked')


def save_image_repost_result(
        search_results: ImageSearchResults,
        uowm: UnitOfWorkManager,
        high_match_check: bool = False,
        source: Text = 'unknown'
) -> NoReturn:
    """
    Take a found repost and save to the database
    :param source: What triggered this search
    :rtype: NoReturn
    :param high_match_check: Perform a high match meme check.
    :param search_results: Set of search results
    :param uowm: Unit of Work Manager
    :return:None
    """
    if not search_results.matches:
        log.debug('Post %s has no matches', search_results.checked_post.post_id)
        return

    with uowm.start() as uow:

        # This is used for ingest repost checking.  If a meme template gets created, it intentionally throws a
        # IngestHighMatchMeme exception.  This will cause celery to retry the task so the newly created meme template
        # gets used
        if high_match_check:
            check_for_high_match_meme(search_results, uowm) # This intentionally throws if we create a meme template

        log.info('Creating repost. Post %s is a repost of %s', search_results.checked_post.url,
                 search_results.matches[0].post.url)

        new_repost = Repost(
            post_id=search_results.checked_post.id,
            repost_of=search_results.matches[0].post,
            author=search_results.checked_post.author,
            search_id=search_results.logged_search.id if search_results.logged_search else None,
            subreddit=search_results.checked_post.subreddit,
            source=source,
            post_type='image'
        )

        try:
            uow.repost.add(new_repost)
        except Exception as e:
            log.error('')
        uow.posts.update(search_results.checked_post)

        try:
            uow.commit()
        except Exception as e:
            log.exception('Failed to save image repost', exc_info=True)

        log.info(' Saved Repost')


def check_for_post_watch(matches: List[SearchMatch], uowm: UnitOfWorkManager) -> List[Dict]:
    results = []
    with uowm.start() as uow:
        for match in matches:
            watches = uow.repostwatch.get_all_active_by_post_id(match.post.id)
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