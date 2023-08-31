import os
from datetime import datetime
from typing import NoReturn

import requests
from praw import Reddit
from sqlalchemy import func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MemeTemplatePotential, \
    MemeTemplate, StatsTopRepost
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.util.helpers import build_markdown_table, \
    chunk_list, get_redis_client
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance, is_bot_banned


def update_ban_list(uowm: UnitOfWorkManager, reddit: Reddit, notification_svc: NotificationService = None) -> None:
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




def remove_expired_bans(uowm: UnitOfWorkManager, notification_svc: NotificationService = None) -> None:
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

def update_banned_sub_wiki(uowm: UnitOfWorkManager, reddit: Reddit) -> None:
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

def update_stat_top_image_repost(uowm: UnitOfWorkManager, reddit: Reddit) -> None:
    days = [1,7,30,365]
    with uowm.start() as uow:
        uow.session.execute('TRUNCATE `stat_top_repost`')
        for day in days:
            result = uow.session.execute(
                'SELECT repost_of, COUNT(*) c FROM repost WHERE post_type=2 AND detected_at > NOW() - INTERVAL :days DAY GROUP BY repost_of_id HAVING c > 1 ORDER BY c DESC LIMIT 2000',
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
                        StatsTopRepost(
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

            post = uow.posts.get_by_id(report.post_id)
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
                post = uow.posts.get_by_id(potential_template.post_id)
                try:
                    meme_hashes = get_image_hashes(post.searched_url, hash_size=32)
                except Exception as e:
                    log.warning('Failed to get meme hash for %s', post.post_id)
                    uow.meme_template_potential.remove(potential_template)
                    uow.commit()
                    continue

                meme_template = MemeTemplate(
                    dhash_h=post.dhash_h,
                    dhash_256=meme_hashes['dhash_h'],
                    post_id=post.id
                )
                uow.meme_template.add(meme_template)
                uow.meme_template_potential.remove(potential_template)
            elif potential_template.vote_total <= -10:
                log.info('Removing potential template with at least 10 negative votes')
                uow.meme_template_potential.remove(potential_template)
            else:
                continue
            uow.commit()

