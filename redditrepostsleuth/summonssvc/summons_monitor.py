import os
import time
from datetime import datetime

from praw import Reddit
from praw.exceptions import APIException
from prawcore import ResponseException, TooManyRequests
from sqlalchemy.exc import DataError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Summons
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler

config = Config()
reddit = get_reddit_instance(config)
uowm = UnitOfWorkManager(get_db_engine(config))
event_logger = EventLogging(config=config)
notification_svc = NotificationService(config)
response_handler = ResponseHandler(reddit, uowm, event_logger, source='summons',
                                   live_response=config.live_responses,
                                   notification_svc=notification_svc)
dup_image_svc = DuplicateImageService(uowm, event_logger, reddit, config=config)
response_builder = ResponseBuilder(uowm)
summons_handler = SummonsHandler(uowm, dup_image_svc, reddit, response_builder,
                                 response_handler, event_logger=event_logger,
                                 summons_disabled=False, notification_svc=notification_svc)


log = get_configured_logger(
    'redditrepostsleuth',
    format='%(asctime)s | Summons Monitor |  %(module)s:%(funcName)s:%(lineno)d | [%(process)d][%(threadName)s] | %(levelname)s: %(message)s'
)

if os.getenv('SENTRY_DNS', None):
    log.info('Sentry DNS set, loading Sentry module')
    import sentry_sdk
    sentry_sdk.init(
        dsn=os.getenv('SENTRY_DNS'),
        environment=os.getenv('RUN_ENV', 'dev')
    )



def handle_summons(summons: Summons) -> None:
    log.info('Starting summons %s ', summons.id)
    with uowm.start() as uow:

        try:
            summons_handler.process_summons(summons)
        except ResponseException as e:
            if e.response.status_code == 429:
                log.warning('IP Rate limit hit.  Waiting', exc_info=False)
                time.sleep(30)
                return
        except AssertionError as e:
            if 'code: 429' in str(e):
                log.warning('Too many requests from IP.  Waiting')
                time.sleep(30)
                return
        except APIException as e:
            if hasattr(e, 'error_type'):
                if e.error_type == 'RATELIMIT':
                    log.error('Hit API rate limit for summons %s on sub %s.', summons.id, summons.post.subreddit)
                    return
                elif e.error_type == 'SOMETHING_IS_BROKEN':
                    summons.reply_failure_reason = 'SOMETHING_IS_BROKEN'
                    uow.commit()
                else:
                    log.error('APIException with unknown error code: %s', e.error_type)
            else:
                log.error('APIException without error_type')
        except Exception as e:
            log.exception('Unknown error')

        log.info('Finished summons %s', summons.id)


def monitor_for_mentions(reddit: Reddit, uowm: UnitOfWorkManager):

    for comment in reddit.inbox.mentions():

        if comment.created_utc < datetime.utcnow().timestamp() - 86400:
            log.debug('Skipping old mention. Created at %s', datetime.fromtimestamp(comment.created_utc))
            continue

        if comment.author.name.lower() in ['sneakpeekbot', 'automoderator']:
            continue

        with uowm.start() as uow:
            existing_summons = uow.summons.get_by_comment_id(comment.id)
            if existing_summons:
                if existing_summons.summons_replied_at:
                    log.debug('Skipping existing mention %s', comment.id)
                    continue
                else:
                    log.info('Summons %s was in database but never responded to.  Handling now', existing_summons.id)
                    handle_summons(existing_summons)
                    continue
            post = uow.posts.get_by_post_id(comment.submission.id)
            if not post:
                log.warning('Failed to find post %s for summons', comment.submission.id)
                continue

            summons = Summons(
                post=post,
                comment_id=comment.id,
                comment_body=comment.body.replace('\\', ''),
                summons_received_at=datetime.fromtimestamp(comment.created_utc),
                requestor=comment.author.name,
                subreddit=comment.subreddit.display_name
            )
            uow.summons.add(summons)
            try:
                uow.commit()
            except DataError as e:
                log.warning('SQLAlchemy Data error saving comment %s: %s', comment.id, e)
                continue

        handle_summons(summons)


if __name__ == '__main__':

    while True:
        try:
            monitor_for_mentions(reddit, uowm)
        except TooManyRequests:
            log.info('Out of API credits')
        time.sleep(int(os.getenv('DELAY', 5)))
