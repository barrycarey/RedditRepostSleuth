import datetime

import requests

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import Subreddit
from redditrepostsleuth.core.exception import UtilApiException
from redditrepostsleuth.core.logging import configure_logger

log = configure_logger(
    name='redditrepostsleuth',
)


@celery.task(bind=True, base=SqlAlchemyTask, autoretry_for=(UtilApiException,), retry_kwards={'max_retries': 50, 'countdown': 600})
def update_subreddit_data(self, subreddit_name) -> None:
    try:
        with self.uowm.start() as uow:
            subreddit = uow.subreddit.get_by_name(subreddit_name)
            url_to_fetch = f'{self.config.util_api}/reddit/subreddit?name={subreddit.name}'
            res = requests.get(url_to_fetch)
            if res.status_code != 200:
                log.error('Bad status %s from util API when checking subreddit %s', res.status_code, subreddit.name)
                raise UtilApiException(f'Bad status {res.status_code} checking {subreddit_name}')

            subreddit_data = res.json()['data']
            subreddit.subscribers = subreddit_data['subscribers'] or 0
            subreddit.nsfw = subreddit_data['over18'] or False
            subreddit.last_checked = datetime.datetime.now(datetime.UTC)
            uow.commit()
            log.debug('Update subreddit data for %s. NSFW: %s - Subscribers: %s', subreddit.name, subreddit.nsfw, subreddit.subscribers)
    except UtilApiException as e:
        raise e
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
def save_subreddit(self, subreddit_name: str):
    try:
        with self.uowm.start() as uow:
            existing = uow.subreddit.get_by_name(subreddit_name)
            if existing:
                log.debug('Subreddit %s already exists', subreddit_name)
                return
            subreddit = Subreddit(name=subreddit_name)
            uow.subreddit.add(subreddit)
            uow.commit()
            log.debug('Saved Subreddit %s', subreddit_name)
            update_subreddit_data.apply_async((subreddit_name,))
    except Exception as e:
        log.exception('')