import logging
from datetime import datetime

from prawcore import Redirect, Forbidden
from sqlalchemy import func

from redditrepostsleuth.adminsvc.bot_comment_monitor import BotCommentMonitor
from redditrepostsleuth.adminsvc.inbox_monitor import InboxMonitor
from redditrepostsleuth.adminsvc.stats_updater import StatsUpdater
from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import RedditTask
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.util.reddithelpers import is_bot_banned, is_sub_mod_praw, bot_has_permission

log = logging.getLogger(__name__)
@celery.task(bind=True, base=RedditTask)
def update_subreddit_stats(self) -> None:
    log.info('Scheduled Task: Update Subreddit Stats')
    stats_updater = StatsUpdater(config=self.config)
    try:
        stats_updater.run_update()
    except Exception as e:
        log.exception('Failed to update subreddit stats')

@celery.task(bind=True, base=RedditTask)
def check_inbox(self) -> None:
    log.info('Scheduled Task: Check Inbox')
    inbox_monitor = InboxMonitor(self.uowm, self.reddit.reddit.reddit, self.response_handler)
    try:
        inbox_monitor.check_inbox()
    except Exception as e:
        log.exception('Failed to update subreddit stats')

@celery.task(bind=True, base=RedditTask)
def check_comments_for_downvotes(self) -> None:
    log.info('Scheduled Task: Check Comment Downvotes')
    comment_monitor = BotCommentMonitor(self.reddit, self.uowm, self.config, notification_svc=self.notification_svc)
    try:
        comment_monitor.check_comments()
    except Exception as e:
        log.exception('Failed to update subreddit stats')


@celery.task(bind=True, base=RedditTask)
def update_subreddit_access_level(self) -> None:
    """
        Go through all monitored subs and update their is_private status
        :return:
        """
    log.info('Scheduled Task: Check Monitored Sub Access Level')
    try:
        with self.uowm.start() as uow:
            monitored_subs: list[MonitoredSub] = uow.monitored_sub.get_all()
            for monitored_sub in monitored_subs:
                try:
                    sub_data = self.reddit.reddit.subreddit(monitored_sub.name)
                    monitored_sub.is_private = True if sub_data.subreddit_type == 'private' else False
                    monitored_sub.nsfw = True if sub_data.over18 else False
                    log.debug('%s: is_private: %s | nsfw: %s', monitored_sub.name, monitored_sub.is_private,
                              monitored_sub.nsfw)
                except (Redirect, Forbidden):
                    log.error('Error getting sub settings')
            uow.commit()
    except Exception as e:
        log.exception('Scheduled Task Failed: Check Monitored Sub Access Level')


@celery.task(bind=True, base=RedditTask)
def update_ban_list(self) -> None:
    """
    Go through banned subs and see if we're still banned
    """
    log.info('Starting Job: Update Subreddit Bans')
    try:
        with self.uowm.start() as uow:
            bans = uow.banned_subreddit.get_all()
            for ban in bans:
                last_checked_delta = (datetime.utcnow() - ban.last_checked).days
                if last_checked_delta < 1:
                    log.debug('Banned sub %s last checked %s days ago.  Skipping', ban.subreddit, last_checked_delta)
                    continue
                if is_bot_banned(ban.subreddit, self.reddit.reddit):
                    log.info('[Subreddit Ban Check] Still banned on %s', ban.subreddit)
                    ban.last_checked = func.utc_timestamp()
                else:
                    log.info('[Subreddit Ban Check] No longer banned on %s', ban.subreddit)
                    uow.banned_subreddit.remove(ban)
                    if self.notification_svc:
                        self.notification_svc.send_notification(
                            f'Removed https://reddit.com/r/{ban.subreddit} from ban list',
                            subject='Subreddit Removed From Ban List!'
                        )
                uow.commit()
    except Exception as e:
        log.exception('Schedule Task Failed: Update Ban List')

@celery.task(bind=True, base=RedditTask)
def update_mod_status(self) -> None:
    """
    Go through all registered subs and check if their a mod and what level of permissions they have
    """
    print('Scheduled Task: Checking Mod Status')
    try:

        with self.uowm.start() as uow:
            monitored_subs: list[MonitoredSub] = uow.monitored_sub.get_all()
            for sub in monitored_subs:
                if not is_sub_mod_praw(sub.name, 'RepostSleuthBot', self.reddit.reddit):
                    log.info('[Mod Check] Bot is not a mod on %s', sub.name)
                    sub.is_mod = False
                    uow.commit()
                    continue

                sub.is_mod = True
                sub.post_permission = bot_has_permission(sub.name, 'posts', self.reddit.reddit)
                sub.wiki_permission = bot_has_permission(sub.name, 'wiki', self.reddit.reddit)
                log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', sub.name, sub.post_permission, sub.wiki_permission)
                uow.commit()
    except Exception as e:
        log.exception('Scheduled Task Failed: Update Mod Status')