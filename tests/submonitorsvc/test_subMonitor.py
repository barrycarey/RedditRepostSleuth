from unittest import TestCase, mock
from unittest.mock import MagicMock

from praw.models import Submission

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSubChecks
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor


class TestSubMonitor(TestCase):

    def test__should_check_post__already_checked_reject(self):
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy'))
        submission = Submission(MagicMock(), id='111')
        monitored_sub_checked_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        monitored_sub_checked_repo.get_by_sub.return_value = MonitoredSubChecks()
        type(uow).monitored_sub_checked = mock.PropertyMock(return_value=monitored_sub_checked_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow

        self.assertFalse(sub_monitor._should_check_post(submission))

