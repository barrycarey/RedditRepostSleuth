import os
from datetime import datetime
from typing import NoReturn, List

import requests
from praw import Reddit
from prawcore import Forbidden, NotFound, Redirect
from sqlalchemy import func

from redditrepostsleuth.core.celery.admin_tasks import check_for_subreddit_config_update_task, \
    update_monitored_sub_stats, check_if_watched_post_is_active
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, StatsTopImageRepost, MemeTemplatePotential, \
    MemeTemplate
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.util.helpers import build_markdown_table, \
    chunk_list, get_redis_client
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance, is_sub_mod_praw, is_bot_banned, \
    bot_has_permission


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
            if not is_sub_mod_praw(sub.name, 'RepostSleuthBot', reddit):
                log.info('[Mod Check] Bot is not a mod on %s', sub.name)
                sub.is_mod = False
                uow.commit()
                continue

            sub.is_mod = True
            sub.post_permission = bot_has_permission(sub.name, 'posts', reddit)
            sub.wiki_permission = bot_has_permission(sub.name, 'wiki', reddit)
            log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', sub.name, sub.post_permission, sub.wiki_permission)
            uow.commit()
    print('[Scheduled Job] Checking Mod Status End')

def update_subreddit_access_level(uowm: UnitOfWorkManager, reddit: Reddit):
    """
    Go through all monitored subs and update their is_private status
    :return:
    """
    log.info('Starting Job: Update subreddit is_private and nsfw')
    with uowm.start() as uow:
        monitored_subs: List[MonitoredSub] = uow.monitored_sub.get_all()
        for monitored_sub in monitored_subs:
            try:
                sub_data = reddit.subreddit(monitored_sub.name)
                monitored_sub.is_private = True if sub_data.subreddit_type == 'private' else False
                monitored_sub.nsfw = True if sub_data.over18 else False
                log.debug('%s: is_private: %s | nsfw: %s', monitored_sub.name, monitored_sub.is_private, monitored_sub.nsfw)
            except (Redirect, Forbidden):
                log.error('Error getting sub settings')
        uow.commit()

def update_ban_list(uowm: UnitOfWorkManager, reddit: Reddit, notification_svc: NotificationService = None) -> NoReturn:
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
            last_checked_delta = (datetime.utcnow() - ban.last_checked).days
            if last_checked_delta < 1:
                log.debug('Banned sub %s last checked %s days ago.  Skipping', ban.subreddit, last_checked_delta)
                continue
            if is_bot_banned(ban.subreddit, reddit):
                log.info('[Subreddit Ban Check] Still banned on %s', ban.subreddit)
                ban.last_checked = func.utc_timestamp()
            else:
                log.info('[Subreddit Ban Check] No longer banned on %s', ban.subreddit)
                uow.banned_subreddit.remove(ban)
                if notification_svc:
                    notification_svc.send_notification(
                        f'Removed https://reddit.com/r/{ban.subreddit} from ban list',
                        subject='Subreddit Removed From Ban List!'
                    )
            uow.commit()


def update_monitored_sub_data(uowm: UnitOfWorkManager) -> NoReturn:
    print('[Scheduled Job] Update Monitored Sub Data')
    with uowm.start() as uow:
        subs = uow.monitored_sub.get_all_active()
        for sub in subs:
            update_monitored_sub_stats.apply_async((sub.name,))

def remove_expired_bans(uowm: UnitOfWorkManager, notification_svc: NotificationService = None) -> NoReturn:
    print('[Scheduled Job] Removed Expired Bans Start')
    with uowm.start() as uow:
        bans = uow.banned_user.get_expired_bans()
        for ban in bans:
            if notification_svc:
                notification_svc.send_notification(
                    f'Removing expired ban for user {ban.name}',
                    subject='**Expired Ban Removed**'
                )
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
                    uow.stats_top_image_repost.add(
                        StatsTopImageRepost(
                            post_id=count_data[0],
                            repost_count=count_data[1],
                            days=day,
                            nsfw=submission.over_18
                        )
                    )
            uow.commit()

def send_reports_to_meme_voting(uowm: UnitOfWorkManager) -> NoReturn:
    with uowm.start() as uow:
        reports = uow.user_report.get_reports_for_voting(7)
        for report in reports:
            if uow.meme_template.get_by_post_id(report.post_id):
                continue
            if uow.meme_template_potential.get_by_post_id(report.post_id):
                continue

            post = uow.posts.get_by_post_id(report.post_id)
            if not post:
                continue
            try:
                if not requests.head(post.searched_url).status_code == 200:
                    continue
            except Exception:
                continue

            potential_template = MemeTemplatePotential(
                post_id=report.post_id,
                submitted_by='background',
                vote_total=0
            )
            uow.meme_template_potential.add(potential_template)
            report.sent_for_voting = True
            uow.commit()

def check_meme_template_potential_votes(uowm: UnitOfWorkManager) -> NoReturn:
    with uowm.start() as uow:
        potential_templates = uow.meme_template_potential.get_all()
        for potential_template in potential_templates:
            if potential_template.vote_total >= 10:
                existing_template = uow.meme_template.get_by_post_id(potential_template.post_id)
                if existing_template:
                    log.info('Meme template already exists for %s. Removing', potential_template.post_id)
                    uow.meme_template_potential.remove(potential_template)
                    uow.commit()
                    return

                log.info('Post %s received %s votes.  Creating meme template', potential_template.post_id, potential_template.vote_total)
                post = uow.posts.get_by_post_id(potential_template.post_id)
                try:
                    meme_hashes = get_image_hashes(post.searched_url, hash_size=32)
                except Exception as e:
                    log.error('Failed to get meme hash for %s', post.post_id)
                    uow.meme_template_potential.remove(potential_template)
                    uow.commit()
                    continue

                meme_template = MemeTemplate(
                    dhash_h=post.dhash_h,
                    dhash_256=meme_hashes['dhash_h'],
                    post_id=post.post_id
                )
                uow.meme_template.add(meme_template)
                uow.meme_template_potential.remove(potential_template)
            elif potential_template.vote_total <= -10:
                log.info('Removing potential template with at least 10 negative votes')
                uow.meme_template_potential.remove(potential_template)
            else:
                continue
            uow.commit()

def queue_config_updates(uowm: UnitOfWorkManager, config: Config) -> NoReturn:
    """
    Send all monitored subs to celery queue to check for config updates
    :param uowm: Unit of Work Manager
    :param config: Config
    :return: None
    """
    print('[Scheduled Job] Queue config update check')
    redis = get_redis_client(config)
    if len(redis.lrange('config_update_check', 0, 20000)) > 0:
        log.info('Config update queue still has pending jobs.  Skipping update queueing ')
        return

    with uowm.start() as uow:
        monitored_subs = uow.monitored_sub.get_all()
        for monitored_sub in monitored_subs:
            check_for_subreddit_config_update_task.apply_async((monitored_sub,))

    print('[Scheduled Job Complete] Queue config update check')


def queue_post_watch_cleanup(uowm: UnitOfWorkManager, config: Config) -> NoReturn:
    """
    Send all watches to celery to check if the post has been deleted
    :param uowm: Unit of work manager
    """
    print('[Scheduled Job] Queue Deleted Watch Check')
    redis = get_redis_client(config)
    if len(redis.lrange('watch_remove_deleted', 0, 20000)) > 0:
        log.info('Deleted watchqueue still has pending jobs.  Skipping update queueing ')
        return

    with uowm.start() as uow:
        watches = uow.repostwatch.get_all()
        for chunk in chunk_list(watches, 30):
            check_if_watched_post_is_active.apply_async((chunk,))

if __name__ == '__main__':
    config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    notification_svc = NotificationService(config)
    reddit = get_reddit_instance(config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    update_ban_list(uowm, reddit, notification_svc)
