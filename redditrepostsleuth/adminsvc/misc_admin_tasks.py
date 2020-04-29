from typing import NoReturn, List

from praw import Reddit

from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import is_moderator, bot_has_permission


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

            sub.post_permission = bot_has_permission(subreddit, 'post')
            sub.wiki_permission = bot_has_permission(subreddit, 'wiki')
            log.info('%s | Post Perm: %s | Wiki Perm: %s', sub.name, sub.post_permission, sub.wiki_permission)
            uow.commit()