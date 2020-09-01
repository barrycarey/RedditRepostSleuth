import time
from typing import Text, NoReturn

from praw import Reddit
from praw.exceptions import APIException
from praw.models import Subreddit
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.util.replytemplates import MONITORED_SUB_ADDED


class NewActivationMonitor:

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit):
        self.uowm = uowm
        self.reddit = reddit

    def check_for_new_invites(self):
        print('[Scheduled Job] Check For Mod Invites Starting')
        try:
            log.info('Checking for new mod invites')
            for msg in self.reddit.inbox.messages(limit=750):
                if 'invitation to moderate' in msg.subject:
                    if self.is_already_active(msg.subreddit.display_name):
                        log.info('%s is already a monitored sub', msg.subreddit.display_name)
                        continue
                    self.activate_sub(msg)
        except Exception as e:
            log.exception('Activation thread died', exc_info=True)


    def accept_invite(self, msg):
        pass

    def activate_sub(self, msg):
        try:
            self._create_monitored_sub_in_db(msg)
        except Exception as e:
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
        self._notify_added(subreddit)
        self._create_wiki_page(subreddit)
        log.info('%s has been added as a monitored sub', subreddit.display_name)

    def _notify_added(self, subreddit: Subreddit) -> NoReturn:
        log.info('Sending sucess PM to %s', subreddit.display_name)
        wiki_url = f'https://www.reddit.com/r/{subreddit.display_name}/about/wiki/repost_sleuth_config'
        try:
            subreddit.message('Repost Sleuth Activated', MONITORED_SUB_ADDED.format(wiki_config=wiki_url))
        except Exception as e:
            log.exception('Failed to send activation PM', exc_info=True)


    def _create_wiki_page(self, subreddit: Subreddit) -> NoReturn:
        template = self._get_wiki_template()
        try:
            subreddit.wiki.create('Repost Sleuth Config', template)
        except Exception as e:
            log.exception('Failed to create wiki page', exc_info=True)

    def _get_wiki_template(self):
        with open('bot_config.md', 'r') as f:
            return f.read()

    def _create_monitored_sub_in_db(self, msg) -> NoReturn:
        with self.uowm.start() as uow:
            monitored_sub = MonitoredSub(
                name=msg.subreddit.display_name,
                active=True,
                repost_only=True,
                report_submission=False,
                report_msg='RepostSleuthBot-Repost',
                target_hamming=5,
                same_sub_only=True,
                sticky_comment=True,
                target_image_match=92,
                meme_filter=False
            )
            uow.monitored_sub.add(monitored_sub)
            try:
                uow.commit()
                log.info('Sub %s added as monitored sub', msg.subreddit.display_name)
            except IntegrityError:
                log.error('Failed to create monitored sub for %s.  It already exists', msg.subreddit.display_name)
            except Exception as e:
                log.exception('Unknown exception saving monitored sub', exc_info=True)
                raise


    def is_already_active(self, subreddit: Text) -> bool:
        with self.uowm.start() as uow:
            existing = uow.monitored_sub.get_by_sub(subreddit)
        return True if existing else False

if __name__ == '__main__':
    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    invite = NewActivationMonitor(uowm, get_reddit_instance(config))
    invite.check_for_new_invites()
