from praw.models import Submission

from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager


class RepostServiceBase:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def find_all_occurrences(self, submission: Submission):
        """
        Find all occurrences of a provided submission
        :param submission: praw.Submission
        """
        raise NotImplementedError

    def process_reposts(self):
        raise NotImplementedError