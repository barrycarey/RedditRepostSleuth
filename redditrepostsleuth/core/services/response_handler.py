from praw import Reddit

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class ResponseHandler:

    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.reddit = reddit

    def leave_comment(self, post_id: str) -> bool:
        pass

    def send_private_message(self, user: str):
        pass

    def _log_response(self, response):
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
        pass