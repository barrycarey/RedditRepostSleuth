from praw import Reddit

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class NewActivationMonitor:

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit):
        self.uowm = uowm
        self.reddit = reddit

    def check_for_new_invites(self):
        pass

    def accept_invite(self):
        pass

    def activate_sub(self):
        pass