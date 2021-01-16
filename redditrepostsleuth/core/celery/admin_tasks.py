from typing import NoReturn, Dict, Text

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AdminTask, RedditTask
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.reddithelpers import get_subscribers, is_sub_mod_praw, get_bot_permissions


@celery.task(bind=True, base=AdminTask)
def check_for_subreddit_config_update_task(self, monitored_sub: MonitoredSub) -> NoReturn:
    self.config_updater.check_for_config_update(monitored_sub, notify_missing_keys=False)

@celery.task(bind=True, base=AdminTask)
def update_subreddit_config_from_database(self, monitored_sub: MonitoredSub, user_data: Dict) -> NoReturn:
    self.config_updater.update_wiki_config_from_database(monitored_sub, notify=True)
    self.config_updater.notification_svc.send_notification(
        f'r/{monitored_sub.name} config updated on site by {user_data["name"]}',
        subject='**Config updated on repostsleuth.com**'
    )


@celery.task(bind=True, base=RedditTask)
def update_monitored_sub_stats(self, sub_name: Text) -> NoReturn:
    with self.uowm.start() as uow:
        sub: MonitoredSub = uow.monitored_sub.get_by_sub(sub_name)
        if not sub:
            log.error('Failed to find subreddit %s', sub_name)
            return

        sub.subscribers = get_subscribers(sub.name, self.reddit.reddit)

        log.info('[Subscriber Update] %s: %s subscribers', sub.name, sub.subscribers)
        sub.is_mod = is_sub_mod_praw(sub.name, 'repostsleuthbot', self.reddit.reddit)
        perms = get_bot_permissions(sub.name, self.reddit) if sub.is_mod else []
        sub.post_permission = True if 'all' in perms or 'posts' in perms else None
        sub.wiki_permission = True if 'all' in perms or 'wiki' in perms else None
        log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', sub.name, sub.post_permission, sub.wiki_permission)
        if sub.is_mod:
            sub.failed_admin_check_count = 0
        uow.commit()

@celery.task(bind=True, base=RedditTask)
def notify_subreddit_removed_mod(self, monitored_sub: MonitoredSub) -> NoReturn:
    message = ''
    if monitored_sub.failed_admin_check_count == 1:
        message = '72 hour notice'
    elif monitored_sub.failed_admin_check_count == 2:
        message = '28 hour notice'
    elif monitored_sub.failed_admin_check_count == 3:
        message = '24 hour notice'
    else:
        message = 'remove'