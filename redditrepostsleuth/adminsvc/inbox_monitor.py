import json
from json import JSONDecodeError
from typing import Text, Dict, NoReturn

from praw import Reddit
from praw.models import Message

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import UserReport
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance


class InboxMonitor:

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit, event_logger: EventLogging = None):
        self.uowm = uowm
        self.event_logger = event_logger
        self.reddit = reddit
        self.failed_checks = []

    def check_inbox(self):
        for msg in self.reddit.inbox.messages(limit=100):
            if msg.author != 'RepostSleuthBot' and msg.subject.lower() in ['false negative', 'false positive']:
                self._process_user_report(msg)

    def _process_user_report(self, msg: Message):
        with self.uowm.start() as uow:
            existing = uow.user_report.get_first_by_message_id(msg.id)
            if existing:
                log.debug('Report %s has already been saved', msg.id)
                return

        report_data = self._load_msg_body_data(msg.body)
        if not report_data:
            log.info('Failed to get report data from message %s.  Not saving', msg.id)
            if len(self.failed_checks) > 10000:
                self.failed_checks = []
            if msg.id not in self.failed_checks:
                self.failed_checks.append(msg.id)
            return

        report = UserReport(
            post_id=report_data['post_id'],
            reported_by=msg.author.name,
            report_type=msg.subject,
            meme_template=report_data['meme_template'],
            msg_body=msg.body,
            message_id=msg.id
        )

        with self.uowm.start() as uow:
            uow.user_report.add(report)
            uow.commit()

        try:
            msg.reply('Thank you for your report. \n\nIt has been documented and will be reviewed further')
        except Exception as e:
            log.exception('Failed to send resposne to report.', exc_info=True)

    def _process_unknown_message(self, msg: Message) -> NoReturn:
        """
        Take an unknown message and forward to dev
        :param msg: Praw Message
        """
        dev = self.reddit.redditor('barrycarey')
        try:
            dev.message(f'FWD: {msg}', f'From {msg.author.name}\n\n{msg.body}')
            msg.reply(
                'Thank you for your message.  This inbox is not monitored.  I have forwarded your message to the developer')
        except Exception as e:
            log.exception('Failed to send message to dev', exc_info=True)

    def _load_msg_body_data(self, body: Text) -> Dict:
        """
        Attempt to load JSON data from provided message body
        :rtype: Dict
        :param body: String of data to load
        :return: Dict
        """
        try:
            return json.loads(body)
        except JSONDecodeError:
            log.error('Failed to load report data from body.  %s', body)

        opening = body.find('{')
        closing = body.find('}')
        if not opening and closing:
            log.error('Failed to find opening and closing brackets in: %s', body)
            return

        try:
            return json.loads(body[opening:closing + 1])
        except JSONDecodeError:
            log.error('Failed to load report data using opening and closing brackets')

if __name__ == '__main__':
    config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    invite = InboxMonitor(uowm, get_reddit_instance(config))
    invite.check_inbox()