from collections import namedtuple
from unittest import TestCase, mock
from unittest.mock import MagicMock, PropertyMock, Mock

from praw.models import Message

from redditrepostsleuth.adminsvc.new_activation_monitor import NewActivationMonitor
from redditrepostsleuth.core.db.databasemodels import MonitoredSub


class TestNewActivationMonitor(TestCase):

    def test_check_for_new_invites_no_invite(self):
        Message = namedtuple('Message', ['subject'])
        m = Message('Hey, you suck')
        reddit = Mock(inbox=Mock(messages=PropertyMock(return_value=[m])))
        with mock.patch.object(NewActivationMonitor, 'activate_sub') as mocked_monitor:
            monitor = NewActivationMonitor(MagicMock(), reddit=reddit)
            monitor.check_for_new_invites()
            mocked_monitor.assert_not_called()

    def test_check_for_new_invites_no_invite(self):
        Message = namedtuple('Message', ['subject'])
        m = Message('invitation to moderate')
        reddit = Mock(inbox=Mock(messages=PropertyMock(return_value=[m])))
        with mock.patch.object(NewActivationMonitor, 'activate_sub') as mocked_monitor:
            monitor = NewActivationMonitor(MagicMock(), reddit=reddit)
            monitor.check_for_new_invites()
            mocked_monitor.assert_called()

    def test__notify_added(self):
        sub_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        sub_repo.get_by_sub.return_value = MonitoredSub(name='testsub')
        type(uow).monitored_sub = mock.PropertyMock(return_value=sub_repo)
        uow.__enter__.return_value = uow
        uow.commit.return_value = None
        uowm.start.return_value = uow
        monitor = NewActivationMonitor(uowm, Mock())
        subreddit = Mock(message=Mock(return_value=None), display_name='testsub')
        monitor._notify_added(subreddit)
        subreddit.message.assert_called()
        self.assertTrue(sub_repo.get_by_sub.activation_notification_sent)

    def test__create_wiki_page(self):
        monitor = NewActivationMonitor(Mock(), Mock())
        subreddit = Mock(wiki=Mock(create=Mock(return_value=None)), display_name='testsub')
        monitor._create_wiki_page(subreddit)
        subreddit.wiki.create.assert_called()

    def test__create_monitored_sub_in_db_already_exists(self):
        sub_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        sub_repo.get_by_sub.return_value = MonitoredSub(name='testsub', id=123)
        type(uow).monitored_sub = mock.PropertyMock(return_value=sub_repo)
        uow.__enter__.return_value = uow
        uow.commit.return_value = None
        uowm.start.return_value = uow
        monitor = NewActivationMonitor(uowm, Mock())
        result = monitor._create_monitored_sub_in_db(Mock(subreddit=Mock(display_name='testsub')))
        self.assertEqual(123, result.id)

    def test__create_monitored_sub_in_db_create(self):
        sub_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        sub_repo.get_by_sub.return_value = None
        type(uow).monitored_sub = mock.PropertyMock(return_value=sub_repo)
        uow.__enter__.return_value = uow
        uow.commit.return_value = None
        uowm.start.return_value = uow
        monitor = NewActivationMonitor(uowm, Mock())
        result = monitor._create_monitored_sub_in_db(Mock(subreddit=Mock(display_name='testsub')))
        self.assertEqual('testsub', result.name)
        uow.commit.assert_called()



    def test_is_already_active_false(self):
        sub_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        sub_repo.get_by_sub.return_value = None
        type(uow).monitored_sub = mock.PropertyMock(return_value=sub_repo)
        uow.__enter__.return_value = uow
        uow.commit.return_value = None
        uowm.start.return_value = uow
        monitor = NewActivationMonitor(uowm, Mock())
        self.assertFalse(monitor.is_already_active('testsub'))

    def test_is_already_active_true(self):
        sub_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        sub_repo.get_by_sub.return_value = MonitoredSub(name='testsub', id=123)
        type(uow).monitored_sub = mock.PropertyMock(return_value=sub_repo)
        uow.__enter__.return_value = uow
        uow.commit.return_value = None
        uowm.start.return_value = uow
        monitor = NewActivationMonitor(uowm, Mock())
        self.assertTrue(monitor.is_already_active('testsub'))


