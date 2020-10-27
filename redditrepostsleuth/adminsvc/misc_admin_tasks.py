import os
from typing import NoReturn, List

from praw import Reddit
from prawcore import Forbidden, NotFound
from sqlalchemy import func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, StatsTopImageRepost
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import is_moderator, bot_has_permission, is_bot_banned, build_markdown_table, \
    chunk_list
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
    print('[Scheduled Job] Checking Mod Status Start')
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
    print('[Scheduled Job] Checking Mod Status End')

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
    print('[Scheduled Job] Update Subscribers Start')
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
                except NotFound:
                    log.error('Sub %s not found', monitored_sub.name)
                log.info('[Subscriber Update] %s: %s subscribers', monitored_sub.name, monitored_sub.subscribers)
                try:
                    uow.commit()
                except Exception as e:
                    log.exception('[Subscriber Update] Failed to update Monitored Sub %s', monitored_sub.name, exc_info=True)
    print('[Scheduled Job] Update Subscribers End')

def remove_expired_bans(uowm: UnitOfWorkManager) -> NoReturn:
    print('[Scheduled Job] Removed Expired Bans Start')
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
    print('[Scheduled Job] Update Ban Wiki Start')
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
    print('[Scheduled Job] Update Ban Wiki End')

def update_top_image_reposts(uowm: UnitOfWorkManager, reddit: Reddit) -> NoReturn:
    days = [1,7,30,365]
    with uowm.start() as uow:
        uow.session.execute('TRUNCATE `stats_top_image_repost`')
        for day in days:
            result = uow.session.execute(
                'SELECT repost_of, COUNT(*) c FROM image_reposts WHERE detected_at > NOW() - INTERVAL :days DAY GROUP BY repost_of HAVING c > 1 ORDER BY c DESC LIMIT 2000',
                {'days': day})
            for chunk in chunk_list(result.fetchall(), 100):
                reddit_ids_to_lookup = []
                for post in chunk:
                    existing = uow.stats_top_image_repost.get_by_post_id_and_days(post[0], day)
                    if existing:
                        existing.repost_count = post[1]
                        continue
                    reddit_ids_to_lookup.append(f't3_{post[0]}')
                for submission in reddit.info(reddit_ids_to_lookup):
                    count_data = next((x for x in chunk if x[0] == submission.id))
                    if not count_data:
                        continue
                    uow.jashpu.add(
                        StatsTopImageRepost(
                            post_id=count_data[0],
                            repost_count=count_data[1],
                            days=day,
                            nsfw=submission.over_18
                        )
                    )
            uow.commit()

if __name__ == '__main__':
    config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    reddit = get_reddit_instance(config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    update_top_image_reposts(uowm, reddit)
