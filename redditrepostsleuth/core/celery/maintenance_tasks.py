import logging

from redditrepostsleuth.adminsvc.bot_comment_monitor import BotCommentMonitor
from redditrepostsleuth.adminsvc.inbox_monitor import InboxMonitor
from redditrepostsleuth.adminsvc.stats_updater import StatsUpdater
from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import RedditTask

log = logging.getLogger(__name__)
@celery.task(bind=True, base=RedditTask)
def update_subreddit_stats(self) -> None:
    stats_updater = StatsUpdater(config=self.config)
    try:
        stats_updater.run_update()
    except Exception as e:
        log.exception('Failed to update subreddit stats')

@celery.task(bind=True, base=RedditTask)
def check_inbox(self) -> None:
    inbox_monitor = InboxMonitor(self.uowm, self.reddit.reddit.reddit, self.response_handler)
    try:
        inbox_monitor.check_inbox()
    except Exception as e:
        log.exception('Failed to update subreddit stats')

@celery.task(bind=True, base=RedditTask)
def check_comments_for_downvotes(self) -> None:
    comment_monitor = BotCommentMonitor(self.reddit, self.uowm, self.config, notification_svc=self.notification_svc)
    try:
        comment_monitor.check_comments()
    except Exception as e:
        log.exception('Failed to update subreddit stats')