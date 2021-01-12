from unittest import TestCase, mock
from unittest.mock import MagicMock

from praw.models import Submission

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSubChecks, Post
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor


class TestSubMonitor(TestCase):

    def test__should_check_post__already_checked_reject(self):
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy'))
        post = Post(left_comment=True)
        self.assertFalse(sub_monitor.should_check_post(post, True, True))

    def test__should_check_post__not_checked_accept(self):
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post = Post(left_comment=False, post_type='image')
        self.assertTrue(sub_monitor.should_check_post(post, True, True))

    def test__should_check_post__reject_crosspost(self):
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post = Post(left_comment=False, post_type='image', crosspost_parent='dkjlsd')
        self.assertFalse(sub_monitor.should_check_post(post, True, True))

    def test__should_check_post__title_filter_accept(self):
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post = Post(left_comment=False, post_type='image', title='some post')
        self.assertTrue(sub_monitor.should_check_post(post, True, True))

    def test__should_check_post__title_filter_reject(self):
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post = Post(left_comment=False, post_type='image', title='some repost')
        self.assertFalse(sub_monitor.should_check_post(post, True, True, title_keyword_filter=['repost']))