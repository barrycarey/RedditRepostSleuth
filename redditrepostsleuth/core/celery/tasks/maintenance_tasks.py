import datetime

import prawcore
import requests
from sqlalchemy.exc import IntegrityError, PendingRollbackError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import Subreddit
from redditrepostsleuth.core.exception import UtilApiException, RateLimitException
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.util.helpers import get_reddit_instance

log = configure_logger(
    name='redditrepostsleuth',
)

class MaintenanceTask(SqlAlchemyTask):
    def __init__(self):
        self.rate_limited_at = None
        super().__init__()
        self.reddit = get_reddit_instance(self.config)

    def is_ratelimited(self):
        if not self.rate_limited_at:
            return False

        delta = datetime.datetime.now(datetime.UTC) - self.rate_limited_at
        if delta.total_seconds() > 120:
            log.info('Removing ratelimit')
            self.rate_limited_at = None
            return False
        #log.info('Rate limited')
        return True


@celery.task(bind=True, base=MaintenanceTask, autoretry_for=(prawcore.exceptions.TooManyRequests,), retry_backoff=60, retry_backoff_max=600, retry_kwargs={'max_retries': 5})
def update_subreddit_data(self, subreddit_name) -> None:
    try:
        with self.uowm.start() as uow:
            subreddit = uow.subreddit.get_by_name(subreddit_name)
            if not subreddit:
                log.warning('Subreddit %s not found in database', subreddit_name)
                return

            # Rate limit: only update once per 24 hours
            if subreddit.last_checked:
                last_checked = subreddit.last_checked
                # Ensure last_checked is timezone-aware for comparison
                if last_checked.tzinfo is None:
                    last_checked = last_checked.replace(tzinfo=datetime.UTC)
                hours_since_update = (datetime.datetime.now(datetime.UTC) - last_checked).total_seconds() / 3600
                if hours_since_update < 24:
                    log.debug('Skipping %s - updated %.1f hours ago', subreddit_name, hours_since_update)
                    return

            # Fetch via PRAW
            try:
                sub = self.reddit.subreddit(subreddit_name)
                _ = sub.subscribers  # Trigger fetch
            except prawcore.exceptions.NotFound:
                log.info('Subreddit %s is deleted', subreddit_name)
                subreddit.deleted = True
                subreddit.last_checked = datetime.datetime.now(datetime.UTC)
                uow.commit()
                return
            except prawcore.exceptions.Forbidden:
                log.info('Subreddit %s is private', subreddit_name)
                subreddit.is_private = True
                subreddit.last_checked = datetime.datetime.now(datetime.UTC)
                uow.commit()
                return

            # Update fields from PRAW
            subreddit.subscribers = sub.subscribers
            subreddit.nsfw = sub.over18
            subreddit.created_at = datetime.datetime.fromtimestamp(sub.created_utc, datetime.UTC)
            subreddit.active_user_count = getattr(sub, 'accounts_active', None)
            subreddit.is_private = sub.subreddit_type == 'private'
            subreddit.deleted = False

            # Extract banner image
            if hasattr(sub, 'banner_background_image') and sub.banner_background_image:
                subreddit.banner_image = sub.banner_background_image.split('?')[0]
            elif hasattr(sub, 'banner_img') and sub.banner_img:
                subreddit.banner_image = sub.banner_img

            # Extract avatar image
            if hasattr(sub, 'community_icon') and sub.community_icon:
                subreddit.avatar_image = sub.community_icon.split('?')[0]
            elif hasattr(sub, 'icon_img') and sub.icon_img:
                subreddit.avatar_image = sub.icon_img

            subreddit.last_checked = datetime.datetime.now(datetime.UTC)
            uow.commit()
            log.debug('Updated subreddit data for %s. NSFW: %s - Subscribers: %s', subreddit.name, subreddit.nsfw, subreddit.subscribers)

            # InfluxDB logging
            influx_data = {
                'measurement': 'Subreddit_Stats',
                'fields': {
                    'subscribers': subreddit.subscribers,
                    'active_user_count': subreddit.active_user_count,
                },
                'tags': {
                    'subreddit': subreddit.name,
                    'nsfw': subreddit.nsfw,
                }
            }
            self.event_logger.write_raw_points([influx_data])

    except prawcore.exceptions.TooManyRequests:
        raise  # Re-raise to trigger autoretry
    except Exception as e:
        log.exception('Failed to update subreddit data for %s', subreddit_name)

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def save_subreddit(self, subreddit_name: str):

    if subreddit_name[:2] == 'u_':
        return
    try:
        with self.uowm.start() as uow:
            existing = uow.subreddit.get_by_name(subreddit_name)
            if existing:
                log.debug('Subreddit %s already exists', subreddit_name)
                if not existing.last_checked:
                    log.info('Sending existing %s for update', subreddit_name)
                    update_subreddit_data.apply_async((subreddit_name,))
                    return

                if not existing.subscribers or existing.subscribers < 20000:
                    return
                elif existing.subscribers > 1000000:
                    delta_days = 1
                elif existing.subscribers > 500000:
                    delta_days = 3
                elif existing.subscribers > 100000:
                    delta_days = 7
                else:
                    delta_days = 30

                log.debug('r/%s - %s - %s', subreddit_name, existing.subscribers, delta_days)

                delta = datetime.datetime.now() - existing.last_checked
                if delta.days > delta_days and existing.subscribers > 10000:
                    log.info('Rechecking r/%s', subreddit_name)
                    update_subreddit_data.apply_async((subreddit_name,))

                return

            subreddit = Subreddit(name=subreddit_name)
            uow.subreddit.add(subreddit)
            uow.commit()
            log.debug('Saved Subreddit %s', subreddit_name)
            update_subreddit_data.apply_async((subreddit_name,))
    except Exception as e:
        log.exception('Failed to save subreddit %s', subreddit_name)


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def save_subreddit_batch(self, subreddit_names: list[str]):
    try:
        with self.uowm.start() as uow:
            for subreddit_name in subreddit_names:
                if subreddit_name[:2] == 'u_':
                    continue
                existing = uow.subreddit.get_by_name(subreddit_name)
                if existing:
                    #log.debug('Subreddit %s already exists', subreddit_name)
                    continue
                subreddit = Subreddit(name=subreddit_name)
                uow.subreddit.add(subreddit)
                update_subreddit_data.apply_async((subreddit_name,))

                try:
                    uow.commit()
                    log.debug('Saved Subreddit %s', subreddit_name)
                except IntegrityError:
                    uow.session.rollback()
                    continue
                except PendingRollbackError as e:
                    uow.session.rollback()

    except Exception as e:
        log.exception('Failed to save subreddit batch of %d names', len(subreddit_names))