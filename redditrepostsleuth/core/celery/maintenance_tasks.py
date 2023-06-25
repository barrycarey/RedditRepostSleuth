import logging

from redditrepostsleuth.adminsvc.bot_comment_monitor import BotCommentMonitor
from redditrepostsleuth.adminsvc.inbox_monitor import InboxMonitor
from redditrepostsleuth.adminsvc.misc_admin_tasks import update_top_image_reposts, send_reports_to_meme_voting, \
    check_meme_template_potential_votes, queue_config_updates, queue_post_watch_cleanup, update_mod_status, \
    update_subreddit_access_level, update_ban_list, remove_expired_bans
from redditrepostsleuth.adminsvc.new_activation_monitor import NewActivationMonitor
from redditrepostsleuth.adminsvc.stats_updater import StatsUpdater
from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.admin_tasks import update_monitored_sub_stats
from redditrepostsleuth.core.celery.basetasks import RedditTask

log = logging.getLogger(__name__)
@celery.task(bind=True, base=RedditTask)
def update_subreddit_stats_task(self) -> None:
    log.info('Scheduled Task: Update Subreddit Stats')
    stats_updater = StatsUpdater(config=self.config)
    try:
        stats_updater.run_update()
    except Exception as e:
        log.exception('Failed to update subreddit stats')


@celery.task(bind=True, base=RedditTask)
def test_task(self) -> None:
    print('Scheduled Task: Test')


@celery.task(bind=True, base=RedditTask)
def check_inbox_task(self) -> None:
    log.info('Scheduled Task: Check Inbox')
    inbox_monitor = InboxMonitor(self.uowm, self.reddit.reddit.reddit, self.response_handler)
    try:
        inbox_monitor.check_inbox()
    except Exception as e:
        log.exception('Failed to update subreddit stats')

@celery.task(bind=True, base=RedditTask)
def check_new_activations_task(self) -> None:
    log.info('Scheduled Task: Checking For Activations')
    activation_monitor = NewActivationMonitor(self.uowm, self.reddit.reddit, notification_svc=self.notification_svc)
    try:
        activation_monitor.check_for_new_invites()
    except Exception as e:
        log.exception('Failed to update subreddit stats')


@celery.task(bind=True, base=RedditTask)
def check_comments_for_downvotes_task(self) -> None:
    log.info('Scheduled Task: Check Comment Downvotes')
    comment_monitor = BotCommentMonitor(self.reddit, self.uowm, self.config, notification_svc=self.notification_svc)
    try:
        comment_monitor.check_comments()
    except Exception as e:
        log.exception('Failed to update subreddit stats')


@celery.task(bind=True, base=RedditTask)
def update_subreddit_access_level_task(self) -> None:
    """
        Go through all monitored subs and update their is_private status
        :return:
        """
    log.info('Starting Job: Post watch cleanup')
    try:
        update_subreddit_access_level(self.uowm, self.reddit.reddit)
    except Exception as e:
        log.exception('Problem in scheduled task')



@celery.task(bind=True, base=RedditTask)
def update_ban_list_task(self) -> None:
    """
    Go through banned subs and see if we're still banned
    """
    log.info('Starting Job: Update Subreddit Bans')
    try:
        update_ban_list(self.uowm, self.reddit.reddit, self.notification_svc)
    except Exception as e:
        log.exception('Problem in scheduled task')

@celery.task(bind=True, base=RedditTask)
def update_mod_status_task(self) -> None:
    """
    Go through all registered subs and check if their a mod and what level of permissions they have
    """
    print('Scheduled Task: Checking Mod Status')
    try:
        update_mod_status(self.uowm, self.reddit.reddit)
    except Exception as e:
        log.exception('Scheduled Task Failed: Update Mod Status')


@celery.task(bind=True, base=RedditTask)
def update_monitored_sub_data_task(self) -> None:
    log.info('Starting Job: Update Subreddit Data')
    try:
        with self.uowm.start() as uow:
            subs = uow.monitored_sub.get_all_active()
            for sub in subs:
                update_monitored_sub_stats.apply_async((sub.name,))
    except Exception as e:
        log.exception('Problem with scheduled task')

@celery.task(bind=True, base=RedditTask)
def remove_expired_bans_task(self) -> None:
    log.info('Starting Job: Remove Expired Bans')
    try:
        remove_expired_bans(self.uowm, self.notification_svc)
    except Exception as e:
        log.exception('Scheduled Task Failed: Update Mod Status')

@celery.task(bind=True, base=RedditTask)
def update_top_image_reposts_task(self) -> None:
    log.info('Starting Job: Remove Expired Bans')
    try:
        update_top_image_reposts(self.uowm, self.reddit.reddit)
    except Exception as e:
        log.exception('Problem in scheduled task')


@celery.task(bind=True, base=RedditTask)
def send_reports_to_meme_voting_task(self):
    log.info('Starting Job: Reports to meme voting')
    try:
        send_reports_to_meme_voting(self.uowm)
    except Exception as e:
        log.exception('Problem in scheduled task')


@celery.task(bind=True, base=RedditTask)
def check_meme_template_potential_votes_task(self):
    log.info('Starting Job: Meme Template Vote')
    try:
        check_meme_template_potential_votes(self.uowm)
    except Exception as e:
        log.exception('Problem in scheduled task')


@celery.task(bind=True, base=RedditTask)
def queue_config_updates_task(self):
    log.info('Starting Job: Config Update Check')
    try:
        queue_config_updates(self.uowm, self.config)
    except Exception as e:
        log.exception('Problem in scheduled task')

@celery.task(bind=True, base=RedditTask)
def queue_post_watch_cleanup_task(self):
    log.info('Starting Job: Post watch cleanup')
    try:
        queue_post_watch_cleanup(self.uowm, self.config)
    except Exception as e:
        log.exception('Problem in scheduled task')