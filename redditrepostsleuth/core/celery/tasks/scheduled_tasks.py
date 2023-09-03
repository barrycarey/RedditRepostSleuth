from praw.exceptions import PRAWException
from prawcore import TooManyRequests

from redditrepostsleuth.adminsvc.bot_comment_monitor import BotCommentMonitor
from redditrepostsleuth.adminsvc.inbox_monitor import InboxMonitor
from redditrepostsleuth.adminsvc.misc_admin_tasks import update_ban_list, \
    remove_expired_bans, update_stat_top_image_repost, send_reports_to_meme_voting, check_meme_template_potential_votes
from redditrepostsleuth.adminsvc.new_activation_monitor import NewActivationMonitor
from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import RedditTask, SqlAlchemyTask, AdminTask
from redditrepostsleuth.core.celery.task_logic.scheduled_task_logic import update_proxies, update_top_reposts, \
    token_checker, run_update_top_reposters, update_top_reposters
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, StatsDailyCount
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod_praw, get_bot_permissions
from redditrepostsleuth.core.util.replytemplates import MONITORED_SUB_MOD_REMOVED_CONTENT, \
    MONITORED_SUB_MOD_REMOVED_SUBJECT

log = configure_logger(
    name='redditrepostsleuth',
)


@celery.task(bind=True, base=RedditTask)
def check_inbox_task(self) -> None:
    print("Checking inbox")
    log.info('Scheduled Task: Check Inbox')
    inbox_monitor = InboxMonitor(self.uowm, self.reddit, self.response_handler)
    try:
        inbox_monitor.check_inbox()
    except TooManyRequests:
        log.warning('[Check Inbox] Out of API credits')
    except Exception as e:
        log.exception('Failed to update subreddit stats')


@celery.task(bind=True, base=RedditTask)
def check_new_activations_task(self) -> None:
    log.info('Scheduled Task: Checking For Activations')
    activation_monitor = NewActivationMonitor(
        self.uowm,
        self.reddit,
        self.response_handler,
        notification_svc=self.notification_svc
    )
    try:
        activation_monitor.check_for_new_invites()
    except TooManyRequests:
        log.warning('[Activation Check] Out of API credits')
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
def update_ban_list_task(self) -> None:
    """
    Go through banned subs and see if we're still banned
    """
    log.info('Starting Job: Update Subreddit Bans')
    try:
        update_ban_list(self.uowm, self.reddit, self.notification_svc)
    except Exception as e:
        log.exception('Problem in scheduled task')


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
    # TODO: Remove
    log.info('Starting Job: Remove Expired Bans')
    try:
        update_stat_top_image_repost(self.uowm, self.reddit)
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

@celery.task(bind=True, base=AdminTask, autoretry_for=(TooManyRequests,), retry_kwards={'max_retries': 3})
def check_for_subreddit_config_update_task(self, monitored_sub: MonitoredSub) -> None:
    self.config_updater.check_for_config_update(monitored_sub, notify_missing_keys=False)

@celery.task(bind=True, base=RedditTask)
def queue_config_updates_task(self):
    log.info('Starting Job: Config Update Check')
    try:
        print('[Scheduled Job] Queue config update check')

        with self.uowm.start() as uow:
            monitored_subs = uow.monitored_sub.get_all()
            for monitored_sub in monitored_subs:
                check_for_subreddit_config_update_task.apply_async((monitored_sub,))

        print('[Scheduled Job Complete] Queue config update check')
    except Exception as e:
        log.exception('Problem in scheduled task')


@celery.task(bind=True, base=SqlAlchemyTask)
def update_daily_stats(self):
    daily_stats = StatsDailyCount()
    try:
        with self.uowm.start() as uow:
            daily_stats.summons_24 = uow.summons.get_count(hours=24)
            daily_stats.summons_total = uow.summons.get_count()
            daily_stats.comments_24h = uow.bot_comment.get_count(hours=24)
            daily_stats.comments_total = uow.bot_comment.get_count()
            daily_stats.link_reposts_24h = uow.repost.get_count(hours=24, post_type=3)
            daily_stats.link_reposts_total = uow.repost.get_count(post_type=3)
            daily_stats.image_reposts_24h = uow.repost.get_count(hours=24, post_type=2)
            daily_stats.image_reposts_total = uow.repost.get_count(hours=24, post_type=2)
            daily_stats.monitored_subreddit_count = uow.monitored_sub.count()
            uow.stat_daily_count.add(daily_stats)
            uow.commit()
            log.info('Updated daily stats')
    except Exception as e:
        log.exception('')



@celery.task(bind=True, base=SqlAlchemyTask)
def update_all_top_reposters_task(self):
    try:
        with self.uowm.start() as uow:
            run_update_top_reposters(uow)
    except Exception as e:
        log.exception('Unknown task error')

@celery.task(bind=True, base=SqlAlchemyTask)
def update_daily_top_reposters_task(self):
    post_types = [1, 2, 3]
    try:
        with self.uowm.start() as uow:
            for post_type_id in post_types:
                update_top_reposters(uow, post_type_id, 1)
    except Exception as e:
        log.exception('Unknown task error')

@celery.task(bind=True, base=SqlAlchemyTask)
def update_top_reposts_task(self):
    try:
        update_top_reposts(self.uowm)
    except Exception as e:
        log.exception('Unknown task exception')



@celery.task(bind=True, base=RedditTask)
def update_monitored_sub_stats(self, sub_name: str) -> None:
    with self.uowm.start() as uow:
        monitored_sub: MonitoredSub = uow.monitored_sub.get_by_sub(sub_name)
        if not monitored_sub:
            log.error('Failed to find subreddit %s', sub_name)
            return
        subreddit = self.reddit.subreddit(monitored_sub.name)
        monitored_sub.subscribers = subreddit.subscribers
        monitored_sub.is_private = True if subreddit.subreddit_type == 'private' else False
        monitored_sub.nsfw = True if subreddit.over18 else False
        log.info('[Subscriber Update] %s: %s subscribers', monitored_sub.name, monitored_sub.subscribers)
        monitored_sub.is_mod = is_sub_mod_praw(monitored_sub.name, 'repostsleuthbot', self.reddit)
        perms = get_bot_permissions(subreddit) if monitored_sub.is_mod else []
        monitored_sub.post_permission = True if 'all' in perms or 'posts' in perms else None
        monitored_sub.wiki_permission = True if 'all' in perms or 'wiki' in perms else None
        log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', monitored_sub.name, monitored_sub.post_permission, monitored_sub.wiki_permission)

        if not monitored_sub.failed_admin_check_count:
            monitored_sub.failed_admin_check_count = 0

        if monitored_sub.is_mod:
            if monitored_sub.failed_admin_check_count > 0:
                self.notification_svc.send_notification(
                    f'Failed admin check for r/{monitored_sub.name} reset',
                    subject='Failed Admin Check Reset'
                )
            monitored_sub.failed_admin_check_count = 0
        else:
            monitored_sub.failed_admin_check_count += 1
            monitored_sub.active = False
            self.notification_svc.send_notification(
                f'Failed admin check for https://reddit.com/r/{monitored_sub.name} increased to {monitored_sub.failed_admin_check_count}.',
                subject='Failed Admin Check Increased'
            )

        if monitored_sub.failed_admin_check_count == 2:
            subreddit = self.reddit.subreddit(monitored_sub.name)
            message = MONITORED_SUB_MOD_REMOVED_CONTENT.format(hours='72', subreddit=monitored_sub.name)
            try:
                self.response_handler.send_mod_mail(
                    subreddit.display_name,
                    message,
                    MONITORED_SUB_MOD_REMOVED_SUBJECT,
                    source='mod_check'
                )
            except PRAWException:
                pass
        elif monitored_sub.failed_admin_check_count >= 4 and monitored_sub.name.lower() != 'dankmemes':
            self.notification_svc.send_notification(
                f'Sub r/{monitored_sub.name} failed admin check 4 times.  Removing',
                subject='Removing Monitored Subreddit'
            )
            uow.monitored_sub.remove(monitored_sub)

        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def update_proxies_task(self) -> None:
    log.info('Starting proxy update')
    try:
        update_proxies(self.uowm)
        log.info('Completed proxy update')
    except Exception as e:
        log.exception('Failed to update proxies')

@celery.task
def update_profile_token_task():
    print('Staring token checker')
    token_checker()