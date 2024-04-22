from celery import Task
from praw.exceptions import RedditAPIException
from praw.models import Comment, Submission
from prawcore import Forbidden, TooManyRequests

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.helpers import get_removal_reason_id
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.util.replytemplates import NO_BAN_PERMISSIONS

log = get_configured_logger(name='redditrepostsleuth')

class RedditActionTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.notification_svc = NotificationService(self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger, live_response=self.config.live_responses)

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def remove_submission_task(self, submission: Submission, removal_reason: str, mod_note: str = None) -> None:
    try:
        removal_reason_id = get_removal_reason_id(removal_reason, submission.subreddit)
        log.info('Attempting to remove post https://redd.it/%s with removal ID %s', submission.id, removal_reason_id)
        submission.mod.remove(reason_id=removal_reason_id, mod_note=mod_note)
    except Forbidden:
        log.error('Failed to remove post https://redd.it/%s, no permission', submission.id)
        send_modmail_task.apply_async(
            (
                submission.subreddit.display_name,
                f'Failed to remove https://redd.it/{submission.id}.\n\nI do not appear to have the required permissions',
                'RepostSleuthBot Missing Permissions'
            )
        )
    except TooManyRequests as e:
        log.warning('Too many requests when removing submission')
        raise e
    except Exception as e:
        log.exception('Failed to remove submission https://redd.it/%s', submission.id, exc_info=True)

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def ban_user_task(self, username: str, subreddit_name: str, ban_reason: str, note: str = None) -> None:
    log.info('Banning user %s from %s', username, subreddit_name)

    try:
        subreddit = self.reddit.subreddit(subreddit_name)
        subreddit.banned.add(username, ban_reason=ban_reason, note=note)
    except TooManyRequests as e:
        log.warning('Too many requests when banning user')
        raise e
    except Forbidden:
        log.warning('Unable to ban user %s on %s.  No permissions', username, subreddit_name)
        message_body = NO_BAN_PERMISSIONS.format(
            username=username,
            subreddit=subreddit_name
        )

        send_modmail_task.apply_async(
            (
                subreddit_name,
                message_body,
                f'Unable To Ban User, No Permissions'
            )
        )
    except RedditAPIException as e:
        if e.error_type == 'TOO_LONG':
            log.warning('Ban reason for subreddit %s is %s and should be no longer than 100', subreddit_name, len(ban_reason))
            send_modmail_task.apply_async(
                (
                    subreddit_name,
                    f'I attempted to ban u/{username} from r/{subreddit_name}.  However, this failed since the ban reason is over 100 characters. \n\nPlease reduce the size of the ban reason. ',
                    'Error When Banning User'
                )
            )
            return
        raise e
    except Exception as e:
        log.exception('Failed to ban %s from %s', username, subreddit_name)

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def lock_submission_task(self, submission: Submission) -> None:
    log.info('Locking submission https://redd.it/%s', submission.id)
    try:
        submission.mod.lock()
    except TooManyRequests as e:
        log.warning('Too many requests when locking submission')
        raise e
    except Forbidden as e:
        log.warning('Failed to lock submission, no permissions on r/%s', submission.subreddit.display_name)
    except Exception as e:
        log.exception('Failed to lock submission https://redd.it/%s', submission.id)
        raise e

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def lock_comment_task(self, comment: Comment) -> None:
    log.info('Locking comment https://reddit.com%s', comment.permalink)
    try:
        comment.mod.lock()
    except TooManyRequests as e:
        log.warning('Too many requests when locking comment')
        raise e
    except Forbidden as e:
        log.warning('Failed to lock comment on r/%s, no permissions', comment.submission.display_name)
    except Exception as e:
        log.exception('')
        raise e

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def sticky_comment_task(self, comment: Comment) -> None:
    log.info('Make comment sticky: https://reddit.com%s ', comment.permalink)
    try:
        comment.mod.distinguish(sticky=True)
    except TooManyRequests as e:
        log.warning('Too many requests when sticky comment')
        raise e
    except Forbidden as e:
        log.warning('Failed to sticky comment on r/%s, no permissions', comment.subreddit.display_name)
    except Exception as e:
        log.exception('')
        raise e

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def mark_as_oc_task(self, submission: Submission) -> None:
    log.info('Marking submission %s as OC', submission.id)
    try:
        submission.mod.set_original_content()
    except TooManyRequests as e:
        log.warning('Too many requests when marking submission OC')
        raise e
    except Forbidden as e:
        log.warning('Failed to mark submission %s as OC on r/%s, no permissions', submission.id, submission.subreddit.display_name)
        send_modmail_task.apply_async(
            (
                submission.subreddit.display_name,
                f'Failed to mark https://redd.it/{submission.id} as OC.\n\nI do not appear to have the required permissions',
                'RepostSleuthBot Missing Permissions'
            )
        )
    except Exception as e:
        log.exception('')
        raise e

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def report_submission_task(self, submission: Submission, report_msg: str) -> None:
    log.info('Reporting submission https://redd.it/%s', submission.id)
    try:
        submission.report(report_msg[:99])  # TODO: Until database column length is fixed
    except TooManyRequests as e:
        log.warning('Too many requests when reporting submission')
        raise e
    except Exception as e:
        log.exception('Failed to report submission %s', submission.id, exc_info=True)
        raise e

@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def leave_comment_task(
        self,
        submission_id: str,
        message: str,
        sticky_comment: bool = False,
        lock_comment: bool = False,
        source: str = 'submonitor'
) -> None:
    try:
        comment = self.response_handler.reply_to_submission(submission_id, message, source)
    except TooManyRequests as e:
        log.warning('Too many requests when removing submission')
        raise e
    except RedditAPIException as e:
        if e.error_type == 'THREAD_LOCKED':
            return
        raise e
    except Exception as e:
        log.exception('Failed to leave comment on submission %s', submission_id)
        return

    if not comment:
        log.debug('No comment returned from response handler')
        return

    if sticky_comment:
        sticky_comment_task.apply_async((comment,))

    if lock_comment:
        lock_comment_task.apply_async((comment,))


@celery.task(
    bind=True,
    ignore_result=True,
    base=RedditActionTask,
    autoretry_for=(TooManyRequests,),
    retry_kwards={'max_retries': 3}
)
def send_modmail_task(self, subreddit_name: str, message: str, subject: str, source: str = 'sub_monitor') -> None:
    log.info('Sending modmail to r/%s', subreddit_name)
    try:
        self.response_handler.send_mod_mail(
            subreddit_name,
            message,
            subject,
            source=source
        )
    except TooManyRequests as e:
        log.warning('Too many requests when sending modmail')
        raise e
    except Exception as e:
        log.exception('Failed to send modmail to %s', subreddit_name)