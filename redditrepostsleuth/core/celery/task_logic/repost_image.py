import logging
from typing import List

from redditrepostsleuth.core.db.databasemodels import Post, RepostWatch
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.replytemplates import WATCH_NOTIFY_OF_MATCH

log = logging.getLogger(__name__)


def check_for_post_watch(matches: list[ImageSearchMatch], uow: UnitOfWork) -> list[dict]:
    results = []
    for match in matches:
        watches = uow.repostwatch.get_all_active_by_post_id(match.match_id)
        if watches:
            log.info('Found %s active watch requests for post %s', len(watches), match.post.post_id)
            for watch in watches:
                results.append({'match': match, 'watch': watch})
    return results


def repost_watch_notify(watches: List[dict[SearchMatch, RepostWatch]], reddit: RedditManager, response_handler: ResponseHandler, repost: Post):
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
            'A post you are watching has been reposted',
            'watch',
        )