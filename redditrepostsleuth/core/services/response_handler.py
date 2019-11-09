from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager


class ResponseHandler:

    def __init__(self, reddit: RedditManager, uowm: UnitOfWorkManager, event_logger: EventLogging, log_response: bool = True):
        self.uowm = uowm
        self.reddit = reddit
        self.log_response = log_response

    def leave_comment(self, submission_id: str, comment_body, send_pm_on_fail: bool = False) -> bool:
        submission = self.reddit.submission(submission_id)
        if not submission:
            return False

        try:
            submission.reply(comment_body)
            self._log_response(comment_body, 'comment')
        except Exception as e:
            log.exception('Failed to leave comment on post https://redd.it/%s', submission_id)
            if send_pm_on_fail:
                pass


    def send_private_message(self, user: str, message_body) -> bool:
        pass

    def _log_response(self, response, response_type: str):
        self._log_response_to_db(response)
        self._log_response_to_influxdb(response)

    def _log_response_to_influxdb(self, response):
        """
        Take a given response and log it to InfluxDB
        :param response:
        """
        pass

    def _log_response_to_db(self, response):
        """
        Take a given response and log it to the database
        :param response:
        """
        with self.uowm.start() as uow:
            uow.bot_comment.add(

            )