import os
from typing import NoReturn, List

from praw import Reddit
from prawcore import Forbidden
from sqlalchemy import func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import is_moderator, bot_has_permission, is_bot_banned, build_markdown_table
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance


def update_mod_status(uowm: UnitOfWorkManager, reddit: Reddit) -> NoReturn:
    """
    Go through all registered subs and check if their a mod and what level of permissions they have
    :param uowm: UnitOfWorkManager
    :param reddit: Rreddit
    """
    ignore_no_mod = [
        'CouldYouDeleteThat',
        'CouldYouDeleteThat',

    ]
    log.info('[Scheduled Job] Checking Mod Status')
    with uowm.start() as uow:
        monitored_subs: List[MonitoredSub] = uow.monitored_sub.get_all()
        for sub in monitored_subs:
            subreddit = reddit.subreddit(sub.name)
            if not subreddit:
                continue
            if not is_moderator(subreddit, 'RepostSleuthBot'):
                log.info('[Mod Check] Bot is not a mod on %s', sub.name)
                sub.is_mod = False
                uow.commit()
                continue

            sub.is_mod = True
            sub.post_permission = bot_has_permission(subreddit, 'post')
            sub.wiki_permission = bot_has_permission(subreddit, 'wiki')
            log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', sub.name, sub.post_permission, sub.wiki_permission)
            uow.commit()


def update_ban_list(uowm: UnitOfWorkManager, reddit: Reddit) -> NoReturn:
    """
    Go through banned subs and see if we're still banned
    :rtype: NoReturn
    :param uowm: UnitOfWorkManager
    :param reddit: Reddit
    """
    log.info('Starting Job: Update Subreddit Bans')
    with uowm.start() as uow:
        bans = uow.banned_subreddit.get_all()
        for ban in bans:
            subreddit = reddit.subreddit(ban.subreddit)
            if is_bot_banned(subreddit):
                log.info('[Subreddit Ban Check] Still banned on %s', ban.subreddit)
                ban.last_checked = func.utc_timestamp()
            else:
                log.info('[Subreddit Ban Check] No longer banned on %s', ban.subreddit)
                uow.banned_subreddit.remove(ban)
            uow.commit()

def update_monitored_sub_subscribers(uowm: UnitOfWorkManager, reddit: Reddit) -> NoReturn:
    log.info('[Scheduled Job] Update Subscribers')
    with uowm.start() as uow:
        subs = uow.monitored_sub.get_all_active()
        for monitored_sub in subs:
            subreddit = reddit.subreddit(monitored_sub.name)
            if subreddit:
                try:
                    monitored_sub.subscribers = subreddit.subscribers
                except Forbidden:
                    log.error('[Subscriber Update] %s: Forbidden error', monitored_sub.name)
                    continue
                log.info('[Subscriber Update] %s: %s subscribers', monitored_sub.name, monitored_sub.subscribers)
                try:
                    uow.commit()
                except Exception as e:
                    log.exception('[Subscriber Update] Failed to update Monitored Sub %s', monitored_sub.name, exc_info=True)

def remove_expired_bans(uowm: UnitOfWorkManager) -> NoReturn:
    log.info('[Scheduled Job] Removed Expired Bans')
    with uowm.start() as uow:
        bans = uow.banned_user.get_expired_bans()
        for ban in bans:
            log.info('[Ban Remover] Removing %s from ban list', ban.name)
            uow.banned_user.remove(ban)
            uow.commit()

def update_banned_sub_wiki(uowm: UnitOfWorkManager, reddit: Reddit) -> NoReturn:
    """
    Update the banned sub wiki page with the most recent list of banned subs
    :param uowm: UnitOfWorkmanager
    :param reddit: Praw Reddit instance
    """
    log.info('[Scheduled Job] Update Ban Wiki')
    wiki_template_file = os.path.join(os.getcwd(), 'banned-subs.md')
    if not os.path.isfile(wiki_template_file):
        log.critical('Unable to locate banned sub wiki file at %s', wiki_template_file)
        return

    with open(wiki_template_file, 'r') as f:
        template = f.read()

    with uowm.start() as uow:
        banned = uow.banned_subreddit.get_all()

    results = [[f'r/{sub.subreddit}', sub.detected_at, sub.last_checked] for sub in banned]
    table_data = build_markdown_table(results, ['Subreddit', 'Detected At', 'Last Checked'])
    wiki = reddit.subreddit('RepostSleuthBot').wiki['published-data/banned-subreddits']
    wiki.edit(template.format(banned_subs=table_data, total=len(banned)))
    log.info('[Banned Sub Wiki Update] Fished update')

if __name__ == '__main__':
    config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    reddit = get_reddit_instance(config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    update_monitored_sub_subscribers(uowm, reddit)
    wiki = reddit.subreddit('RepostSleuthBot').wiki['published-data/banned-subreddits']
    build_markdown_table([['test1', 'test2', 'test3']], ['header1', 'header2', 'header3'])



    remove_expired_bans(uowm)