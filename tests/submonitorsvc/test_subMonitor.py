from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub, PostType
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor


class TestSubMonitor(TestCase):

    def test__should_check_post__not_checked_accept(self):
        monitored_sub = MonitoredSub(check_image_posts=True, check_link_posts=True, check_text_posts=True)
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post_type = PostType(name='image')
        post = Post(post_type=post_type)
        self.assertTrue(sub_monitor.should_check_post(post, monitored_sub))

    def test__should_check_post__reject_crosspost(self):
        monitored_sub = MonitoredSub(check_image_posts=True, check_link_posts=True, check_text_posts=True)
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post_type = PostType(name='image')
        post = Post(post_type=post_type, is_crosspost=True)
        self.assertFalse(sub_monitor.should_check_post(post, monitored_sub))

    def test__should_check_post__title_filter_accept(self):
        monitored_sub = MonitoredSub(check_image_posts=True, check_link_posts=True, check_text_posts=True)
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post_type = PostType(name='image')
        post = Post(post_type=post_type, title='some post')
        self.assertTrue(sub_monitor.should_check_post(post, monitored_sub))

    def test__should_check_post__title_filter_reject(self):
        monitored_sub = MonitoredSub(check_image_posts=True, check_link_posts=True, check_text_posts=True)
        sub_monitor = SubMonitor(MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(), config=Config(redis_host='dummy',supported_post_types=['image']))
        post_type = PostType(name='image')
        post = Post(post_type=post_type, title='some repost')
        self.assertFalse(sub_monitor.should_check_post(post, monitored_sub, title_keyword_filter=['repost']))

    def test__send_mod_mail_not_enabled(self):
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())
        mock_monitored_sub = Mock(send_repost_modmail=False)
        sub_monitor._send_mod_mail(mock_monitored_sub, 'test')
        mock_response_handler.send_mod_mail.assert_not_called()

    @patch('redditrepostsleuth.submonitorsvc.submonitor.len')
    def test__send_mod_mail_not_enabled(self, mock_len):
        mock_len.return_value = 5
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())
        monitored_sub = MonitoredSub(name='testsubreddit', send_repost_modmail=True)
        sub_monitor._send_mod_mail(monitored_sub, Mock(matches=[], checked_post=Mock(post_id='abc123')))
        expected_message_body = 'Post [https://redd.it/abc123](https://redd.it/abc123) looks like a repost. I found 5 matches'
        mock_response_handler.send_mod_mail.assert_called_with('testsubreddit', expected_message_body, 'Repost found in r/testsubreddit', source='Submonitor')