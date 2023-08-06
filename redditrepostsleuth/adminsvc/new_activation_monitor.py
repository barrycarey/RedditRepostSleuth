import json
import logging
from typing import Text, NoReturn

from praw import Reddit
from praw.exceptions import APIException, RedditAPIException
from praw.models import Subreddit, Message

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.default_bot_config import DEFAULT_CONFIG_VALUES
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.util.replytemplates import MONITORED_SUB_ADDED

log = logging.getLogger(__name__)

class NewActivationMonitor:

    def __init__(
            self,
            uowm: UnitOfWorkManager,
            reddit: Reddit,
            response_handler: ResponseHandler,
            notification_svc: NotificationService = None):
        self.notification_svc = notification_svc
        self.uowm = uowm
        self.reddit = reddit
        self.response_handler = response_handler

    def check_for_new_invites(self):
        for msg in self.reddit.inbox.messages(limit=1000):
            if 'invitation to moderate' in msg.subject:
                log.info('Found invitation for %s', msg.subreddit.display_name)
                self.activate_sub(msg)



    def activate_sub(self, msg: Message):
        # TODO: API Reduction - No need to call Reddit API after seeing int exists in DB
        try:
            monitored_sub = self._create_monitored_sub_in_db(msg)
        except Exception as e:
            log.exception('Failed to save new monitored sub', exc_info=True)
            return
        subreddit = self.reddit.subreddit(msg.subreddit.display_name)
        try:
            subreddit.mod.accept_invite()
        except APIException as e:
            if e.error_type == 'NO_INVITE_FOUND':
                log.error('No open invite to %s', msg.subreddit.display_name)
            return
        except Exception as e:
            log.exception('Failed to accept invite', exc_info=True)
            return
        if not monitored_sub.activation_notification_sent:
            self._notify_added(subreddit)
        self._create_wiki_page(subreddit)
        if self.notification_svc:
            self.notification_svc.send_notification(
                f'Added new monitored sub r/{monitored_sub.name}',
                subject='New Monitored Sub Added!'
            )
        log.info('%s has been added as a monitored sub', subreddit.display_name)

    def _notify_added(self, subreddit: Subreddit) -> NoReturn:
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit.display_name)
            log.info('Sending success PM to %s', subreddit.display_name)
            wiki_url = f'https://www.reddit.com/r/{subreddit.display_name}/wiki/repost_sleuth_config'
            try:
                self.response_handler.send_mod_mail(
                    subreddit.display_name,
                    MONITORED_SUB_ADDED.format(wiki_config=wiki_url),
                    'Repost Sleuth Activated',
                    source='activation'
                )
                monitored_sub.activation_notification_sent = True
            except RedditAPIException as e:
                log.exception('Failed to send activation PM', exc_info=True)
            uow.commit()

    def _create_wiki_page(self, subreddit: Subreddit) -> NoReturn:
        template = json.dumps(DEFAULT_CONFIG_VALUES)
        try:
            subreddit.wiki.create('Repost Sleuth Config', template)
        except RedditAPIException:
            log.exception('Failed to create wiki page', exc_info=True)

    def _create_monitored_sub_in_db(self, msg: Message) -> MonitoredSub:
        with self.uowm.start() as uow:
            existing = uow.monitored_sub.get_by_sub(msg.subreddit.display_name)
            if existing:
                return existing
            monitored_sub = MonitoredSub(**{**DEFAULT_CONFIG_VALUES, **{'name': msg.subreddit.display_name}})
            uow.monitored_sub.add(monitored_sub)
            try:
                uow.commit()
                log.info('Sub %s added as monitored sub', msg.subreddit.display_name)
            except Exception as e:
                log.exception('Unknown exception saving monitored sub', exc_info=True)
                raise
        return monitored_sub

    def is_already_active(self, subreddit: Text) -> bool:
        with self.uowm.start() as uow:
            existing = uow.monitored_sub.get_by_sub(subreddit)
        return True if existing else False

if __name__ == '__main__':
    config = Config(r'C:/users/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = UnitOfWorkManager(get_db_engine(config))
    invite = NewActivationMonitor(uowm, get_reddit_instance(config))
    while True:
        invite.check_for_new_invites()
