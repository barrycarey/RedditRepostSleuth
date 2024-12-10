import datetime
from functools import wraps
from time import perf_counter

import requests
from prawcore import TooManyRequests, Redirect, ServerError, NotFound

from redditrepostsleuth.adminsvc.bot_comment_monitor import BotCommentMonitor
from redditrepostsleuth.adminsvc.inbox_monitor import InboxMonitor
from redditrepostsleuth.adminsvc.misc_admin_tasks import update_ban_list, \
    remove_expired_bans, update_stat_top_image_repost, send_reports_to_meme_voting, check_meme_template_potential_votes
from redditrepostsleuth.adminsvc.new_activation_monitor import NewActivationMonitor
from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import RedditTask, SqlAlchemyTask, AdminTask
from redditrepostsleuth.core.celery.task_logic.scheduled_task_logic import update_proxies, token_checker, \
    run_update_top_reposters, update_top_reposters, update_monitored_sub_data, run_update_top_reposts
from redditrepostsleuth.core.db.databasemodels import StatsDailyCount
from redditrepostsleuth.core.exception import UtilApiException
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.util.helpers import chunk_list

log = configure_logger(
    name='redditrepostsleuth',
)

def get_task_influx_points(task_name: str, task_status: str, task_runtime: float):
    return ([
        {
            'measurement': 'Scheduled_Task_Updates',
            'time': datetime.datetime.now(datetime.UTC),
            'fields': {
                'run_time': task_runtime
            },
            'tags': {
                'task_name': task_name,
                'task_status': task_status
            }
        }
    ])

def record_task_status(func):
    @wraps(func)
    def dec(self, *args, **kwargs):
        if not hasattr(self, 'event_logger'):
            log.warning('Task class %s does not have an event logger, cannot record task time', self.__name__)
            return func(self, *args, **kwargs)

        try:
            task_start = perf_counter()
            self.event_logger.write_raw_points(
                get_task_influx_points(
                    func.__name__,
                    'started',
                    0.0,
                )
            )
            func(self, *args, **kwargs)
            task_status = 'finished'

        except Exception as e:
            log.exception('')
            task_status = 'failed'

        self.event_logger.write_raw_points(
            get_task_influx_points(
                func.__name__,
                task_status,
                perf_counter() - task_start,
            )
        )
    return dec



@celery.task(bind=True, base=RedditTask)
@record_task_status
def check_inbox_task(self) -> None:
    log.info('Scheduled Task: Check Inbox')

    inbox_monitor = InboxMonitor(self.uowm, self.reddit, self.response_handler)
    try:
        inbox_monitor.check_inbox()
    except TooManyRequests:
        log.warning('[Check Inbox] Out of API credits')
    except Exception as e:
        log.exception('Failed to update subreddit stats')



@celery.task(bind=True, base=RedditTask)
@record_task_status
def check_new_activations_task(self) -> None:
    log.debug('Scheduled Task: Checking For Activations')
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
@record_task_status
def check_comments_for_downvotes_task(self) -> None:
    # TODO: Remove, no longer used
    log.info('Scheduled Task: Check Comment Downvotes')
    comment_monitor = BotCommentMonitor(self.reddit, self.uowm, self.config, notification_svc=self.notification_svc)
    try:
        comment_monitor.check_comments()
    except Exception as e:
        log.exception('Failed to update subreddit stats')

@celery.task(bind=True, base=RedditTask)
@record_task_status
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
@record_task_status
def update_monitored_sub_data_task(self) -> None:
    log.debug('Starting Job: Update Subreddit Data')
    try:
        with self.uowm.start() as uow:
            subs = uow.monitored_sub.get_all()
            for sub in subs:
                update_monitored_sub_stats_task.apply_async((sub.name,))
    except Exception as e:
        log.exception('Problem with scheduled task')


@celery.task(bind=True, base=RedditTask)
@record_task_status
def remove_expired_bans_task(self) -> None:
    log.info('Starting Job: Remove Expired Bans')
    try:
        remove_expired_bans(self.uowm, self.notification_svc)
    except Exception as e:
        log.exception('Scheduled Task Failed: Update Mod Status')

@celery.task(bind=True, base=RedditTask)
@record_task_status
def send_reports_to_meme_voting_task(self):
    log.info('Starting Job: Reports to meme voting')
    try:
        send_reports_to_meme_voting(self.uowm)
    except Exception as e:
        log.exception('Problem in scheduled task')


@celery.task(bind=True, base=RedditTask)
@record_task_status
def check_meme_template_potential_votes_task(self):
    log.info('Starting Job: Meme Template Vote')
    try:
        check_meme_template_potential_votes(self.uowm)
    except Exception as e:
        log.exception('Problem in scheduled task')


@celery.task(bind=True, base=AdminTask, autoretry_for=(TooManyRequests,), retry_kwards={'max_retries': 3})
@record_task_status
def check_for_subreddit_config_update_task(self, subreddit_name: str) -> None:
    with self.uowm.start() as uow:

        try:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit_name)
            self.config_updater.check_for_config_update(monitored_sub, notify_missing_keys=False)
        except TooManyRequests:
            raise
        except NotFound:
            log.warning('NotFound error when updating config for %s', monitored_sub.name)
            return
        except Redirect as e:
            if str(e) == 'Redirect to /subreddits/search':
                log.warning('Subreddit %s no longer exists.  Setting to inactive in database', monitored_sub.name)
                monitored_sub.active = False
                uow.commit()
        except Exception as e:
            log.exception('')

@celery.task(bind=True, base=RedditTask)
@record_task_status
def queue_config_updates_task(self):
    """
    Goes through each registered subreddit and queues a job to check their Wiki config for updates
    :param self:
    """
    log.info('Starting Job: Config Update Check')
    try:
        print('[Scheduled Job] Queue config update check')

        with self.uowm.start() as uow:
            monitored_subs = uow.monitored_sub.get_all_active()
            for monitored_sub in monitored_subs:
                check_for_subreddit_config_update_task.apply_async((monitored_sub.name,))

        print('[Scheduled Job Complete] Queue config update check')
    except Exception as e:
        log.exception('Problem in scheduled task')


@celery.task(bind=True, base=SqlAlchemyTask)
@record_task_status
def update_daily_stats(self):
    log.info('[Daily Stat Update] Started')
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
            daily_stats.image_reposts_total = uow.repost.get_count(post_type=2)
            daily_stats.monitored_subreddit_count = uow.monitored_sub.get_count()
            uow.stat_daily_count.add(daily_stats)
            uow.commit()
            log.info('[Daily Stat Update] Finished')
    except Exception as e:
        log.exception('Problem updating stats')


@celery.task(bind=True, base=SqlAlchemyTask)
@record_task_status
def update_all_top_reposts_task(self):
    try:
        with self.uowm.start() as uow:
            run_update_top_reposts(uow)
    except Exception as e:
        log.exception('Unknown task error')

@celery.task(bind=True, base=SqlAlchemyTask)
@record_task_status
def update_all_top_reposters_task(self):
    try:
        with self.uowm.start() as uow:
            run_update_top_reposters(uow)
    except Exception as e:
        log.exception('Unknown task error')

@celery.task(bind=True, base=SqlAlchemyTask)
@record_task_status
def update_daily_top_reposters_task(self):
    post_types = [1, 2, 3]
    try:
        with self.uowm.start() as uow:
            for post_type_id in post_types:
                update_top_reposters(uow, post_type_id, 1)
    except Exception as e:
        log.exception('Unknown task error')


@celery.task(bind=True, base=RedditTask, autoretry_for=(TooManyRequests,), retry_kwards={'max_retries': 3})
@record_task_status
def update_monitored_sub_stats_task(self, sub_name: str) -> None:
    try:
        with self.uowm.start() as uow:
            update_monitored_sub_data(
                uow,
                sub_name,
                self.reddit,
                self.notification_svc,
                self.response_handler
            )
    except TooManyRequests:
        raise
    except ServerError as e:
        log.warning('Server error checking %s', sub_name)
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask)
@record_task_status
def update_proxies_task(self) -> None:
    log.info('Starting proxy update')
    try:
        update_proxies(self.uowm)
        log.info('Completed proxy update')
    except Exception as e:
        log.exception('Failed to update proxies')


@celery.task(bind=True, base=SqlAlchemyTask)
@record_task_status
def delete_search_batch(self, ids: list[int]):
    try:
        with self.uowm.start() as uow:
            log.info('Starting range %s:%s', ids[0], ids[-1])
            for id in ids:
                search = uow.repost_search.get_by_id(id)
                if search:
                    log.debug('Deleting search %s', search.id)
                    uow.repost_search.remove(search)
            uow.commit()
            log.info('Finished range %s:%s', ids[0], ids[-1])
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask)
@record_task_status
def queue_search_history_cleanup(self):
    with self.uowm.start() as uow:
        searches = uow.repost_search.get_all_ids_older_than_days(120, limit=100000000)
        if not searches:
            log.info('No search history to cleanup')
            return
        log.info('Queuing Search History Cleanup.  Range: ID Range: %s:%s', searches[0].id, searches[-1].id)
        ids = [x[0] for x in searches]
        for chunk in chunk_list(ids, 5000):
            delete_search_batch.apply_async((chunk,))

@celery.task(bind=True, base=RedditTask, autoretry_for=(UtilApiException,), retry_kwards={'max_retries': 5})
@record_task_status
def queue_subreddit_data_updates(self) -> None:
    with self.uowm.start() as uow:
        subreddits_to_update = uow.subreddit.get_subreddits_to_update()
        for subreddit in subreddits_to_update:
            celery.send_task('redditrepostsleuth.core.celery.tasks.maintenance_tasks.save_subreddit',
                             args=[subreddit.name])