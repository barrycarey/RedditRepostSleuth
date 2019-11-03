from praw.models import Submission

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class RepostServiceBase:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def find_all_occurrences(self, submission: Submission):
        """
        Find all occurrences of a provided submission
        :param submission: praw.Submission
        """
        raise NotImplementedError

    def repost_check(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError
