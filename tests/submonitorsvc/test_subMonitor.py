from unittest import TestCase, mock
from unittest.mock import MagicMock

from praw.models import Submission

from redditrepostsleuth.core.db.databasemodels import MonitoredSubChecks
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor


class TestSubMonitor(TestCase):
    def test__check_sub(self):
        self.fail()

    def test__check_for_repost(self):
        self.fail()

    def test__mod_actions(self):
        self.fail()

    def test__sticky_reply(self):
        self.fail()

    def test__report_submission(self):
        self.fail()

    def test__leave_comment(self):
        self.fail()

    def test__save_unknown_post(self):
        self.fail()

    def test__should_check_post__already_checked_reject(self):
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(),)
        submission = Submission(MagicMock(), id='111')
        monitored_sub_checked_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        monitored_sub_checked_repo.get_by_sub.return_value = MonitoredSubChecks()
        type(uow).monitored_sub_checked = mock.PropertyMock(return_value=monitored_sub_checked_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow

        self.assertFalse(sub_monitor._should_check_post(submission))

    def test__should_check_post__not_checked_accept(self):

        submission = Submission(MagicMock(), id='111')
        monitored_sub_checked_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        monitored_sub_checked_repo.get_by_sub.return_value = None
        type(uow).monitored_sub_checked = mock.PropertyMock(return_value=monitored_sub_checked_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow
        sub_monitor = SubMonitor(MagicMock(), uowm, MagicMock(), MagicMock(), MagicMock(), )

        self.assertTrue(sub_monitor._should_check_post(submission))