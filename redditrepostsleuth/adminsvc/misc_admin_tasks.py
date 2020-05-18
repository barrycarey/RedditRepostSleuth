from typing import NoReturn, List

from praw import Reddit
from sqlalchemy import func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import is_moderator, bot_has_permission, is_bot_banned
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance


def update_mod_status(uowm: UnitOfWorkManager, reddit: Reddit) -> NoReturn:
    """
    Go through all registered subs and check if their a mod and what level of permissions they have
    :param uowm: UnitOfWorkManager
    :param reddit: Rreddit
    """
    with uowm.start() as uow:
        monitored_subs: List[MonitoredSub] = uow.monitored_sub.get_all()
        for sub in monitored_subs:
            subreddit = reddit.subreddit(sub.name)
            if not subreddit:
                continue
            if not is_moderator(subreddit, 'RepostSleuthBot'):
                log.info('Bot is not a mod on %s', sub.name)
                sub.is_mod = False
                uow.commit()
                continue

            sub.is_mod = True
            sub.post_permission = bot_has_permission(subreddit, 'post')
            sub.wiki_permission = bot_has_permission(subreddit, 'wiki')
            log.info('%s | Post Perm: %s | Wiki Perm: %s', sub.name, sub.post_permission, sub.wiki_permission)
            uow.commit()


def update_ban_list(uowm: UnitOfWorkManager, reddit: Reddit) -> NoReturn:
    """
    Go through banned subs and see if we're still banned
    :rtype: NoReturn
    :param uowm: UnitOfWorkManager
    :param reddit: Reddit
    """
    with uowm.start() as uow:
        bans = uow.banned_subreddit.get_all()
        for ban in bans:
            subreddit = reddit.subreddit(ban.subreddit)
            if is_bot_banned(subreddit):
                log.info('Still banned on %s', ban.subreddit)
                ban.last_checked = func.utc_timestamp()
            else:
                log.info('No longer banned on %s', ban.subreddit)
                uow.banned_subreddit.remove(ban)
            uow.commit()

if __name__ == '__main__':
    config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    reddit = get_reddit_instance(config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    update_ban_list(uowm, reddit)