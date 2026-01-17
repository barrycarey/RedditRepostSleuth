import datetime

import requests
from sqlalchemy.exc import IntegrityError, PendingRollbackError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import Subreddit
from redditrepostsleuth.core.exception import UtilApiException, RateLimitException
from redditrepostsleuth.core.logging import configure_logger

log = configure_logger(
    name='redditrepostsleuth',
)

class MaintenanceTask(SqlAlchemyTask):
    def __init__(self):
        self.rate_limited_at = None
        super().__init__()

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


@celery.task(bind=True, base=MaintenanceTask, autoretry_for=(UtilApiException,RateLimitException), retry_kwards={'max_retries': 50, 'countdown': 1800})
def update_subreddit_data(self, subreddit_name) -> None:
    if self.is_ratelimited():
        raise RateLimitException('Ratelimited')
    try:

        with self.uowm.start() as uow:
            subreddit = uow.subreddit.get_by_name(subreddit_name)
            url_to_fetch = f'{self.config.util_api}/reddit/subreddit?name={subreddit.name}'
            res = requests.get(url_to_fetch)
            subreddit.last_checked = datetime.datetime.now(datetime.UTC)
            if res.status_code == 404:
                log.info('Subreddit %s is deleted', subreddit_name)
                subreddit.deleted = True
                uow.commit()
                return
            elif res.status_code == 403:
                subreddit.is_private = True
                uow.commit()
                return
            elif res.status_code == 429:
                log.warning('New Rate limit')
                self.rate_limited_at = datetime.datetime.now(datetime.UTC)
                raise UtilApiException(f'Bad status {res.status_code} checking {subreddit_name}')
            elif res.status_code != 200:
                log.warning('Bad status %s from util API when checking subreddit %s', res.status_code, subreddit.name)
                return
                #raise UtilApiException(f'Bad status {res.status_code} checking {subreddit_name}')

            subreddit_data = res.json()['data']
            subreddit.subscribers = subreddit_data['subscribers'] if 'subscribers' in subreddit_data else None
            subreddit.nsfw = subreddit_data['over18'] if 'over18' in subreddit_data else None
            if 'created_utc' in subreddit_data:
                subreddit.created_at = datetime.datetime.fromtimestamp(subreddit_data['created_utc'], datetime.UTC)
            if 'active_user_count' in subreddit_data:
                subreddit.active_user_count = subreddit_data['active_user_count']
            subreddit.deleted = False
            uow.commit()
            log.debug('Update subreddit data for %s. NSFW: %s - Subscribers: %s', subreddit.name, subreddit.nsfw, subreddit.subscribers)

            influx_data = {
                'measurement': 'Subreddit_Stats',
                # 'time': datetime.utcnow().timestamp(),
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

    except UtilApiException as e:
        raise e
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
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
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
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
        log.exception('')