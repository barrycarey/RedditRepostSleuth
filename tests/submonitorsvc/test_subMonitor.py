from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch, ANY

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub, PostType, UserReview, UserWhitelist
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
        mock_response_handler.send_mod_mail.assert_called_with('testsubreddit', ANY, 'Repost found in r/testsubreddit', source='sub_monitor')

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_only_fans_normal_user_no_action(self, mock_ban_user, mock_remove_post):
        user_review = UserReview(content_links_found=0, username='test_user')
        post = Post(subreddit='test_subreddit', author='test_user')
        monitored_sub = MonitoredSub(name='test_subreddit', adult_promoter_remove_post=True, adult_promoter_ban_user=True)
        mock_uow = MagicMock(user_review=MagicMock(get_by_username=MagicMock(return_value=user_review)))
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())

        sub_monitor.handle_only_fans_check(post, mock_uow, monitored_sub)

        mock_ban_user.assert_not_called()
        mock_remove_post.assert_not_called()

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_only_fans_user_not_found_no_action(self, mock_ban_user, mock_remove_post):
        post = Post(subreddit='test_subreddit', author='test_user')
        monitored_sub = MonitoredSub(name='test_subreddit', adult_promoter_remove_post=True, adult_promoter_ban_user=True)
        mock_uow = MagicMock(
            user_review=MagicMock(get_by_username=MagicMock(return_value=None)),
            user_whitelist=MagicMock(get_by_username_and_subreddit=MagicMock(return_value=None))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())

        sub_monitor.handle_only_fans_check(post, mock_uow, monitored_sub)

        mock_uow.user_review.get_by_username.assert_called_once_with('test_user')
        mock_ban_user.assert_not_called()
        mock_remove_post.assert_not_called()

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_only_fans_flagged_user_ban_user(self, mock_ban_user, mock_remove_post):
        user_review = UserReview(content_links_found=1, username='test_user', notes='Profile links match onlyfans.com')
        post = Post(subreddit='test_subreddit', author='test_user')
        monitored_sub = MonitoredSub(name='test_subreddit', adult_promoter_remove_post=False, adult_promoter_ban_user=True)
        mock_uow = MagicMock(
            user_review=MagicMock(get_by_username=MagicMock(return_value=user_review)),
            user_whitelist=MagicMock(get_by_username_and_subreddit=MagicMock(return_value=None))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())

        sub_monitor.handle_only_fans_check(post, mock_uow, monitored_sub)

        mock_ban_user.assert_called_once_with('test_user', 'test_subreddit', 'Profile links match onlyfans.com')
        mock_remove_post.assert_not_called()

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_only_fans_flagged_user_remove_post(self, mock_ban_user, mock_remove_post):
        user_review = UserReview(content_links_found=1, username='test_user', notes='Profile links match onlyfans.com')
        post = Post(subreddit='test_subreddit', author='test_user')
        monitored_sub = MonitoredSub(name='test_subreddit', adult_promoter_remove_post=True, adult_promoter_ban_user=False)
        mock_uow = MagicMock(
            user_review=MagicMock(get_by_username=MagicMock(return_value=user_review)),
            user_whitelist=MagicMock(get_by_username_and_subreddit=MagicMock(return_value=None))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())

        sub_monitor.handle_only_fans_check(post, mock_uow, monitored_sub)

        mock_ban_user.assert_not_called()
        mock_remove_post.assert_called_once_with(monitored_sub, ANY)

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_high_volume_reposter_check_under_threshold_no_action(self, mock_ban_user, mock_remove_post):
        mock_uow = MagicMock(
            stat_top_reposter=MagicMock(get_total_reposts_by_author_and_day_range=MagicMock(return_value=50))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())
        monitored_sub = MonitoredSub(
            name='test_subreddit',
            high_volume_reposter_ban_user=True,
            high_volume_reposter_threshold=100,
            high_volume_reposter_notify_mod_mail=False,
            high_volume_reposter_remove_post=False
        )
        post = Post(subreddit='test_subreddit', author='test_user')
        sub_monitor.handle_high_volume_reposter_check(post, mock_uow, monitored_sub)
        mock_ban_user.assert_not_called()
        mock_remove_post.assert_not_called()
        mock_response_handler.send_mod_mail.assert_not_called()

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_high_volume_reposter_check_over_threshold_remove(self, mock_ban_user, mock_remove_post):
        mock_uow = MagicMock(
            stat_top_reposter=MagicMock(get_total_reposts_by_author_and_day_range=MagicMock(return_value=200)),
            user_whitelist=MagicMock(get_by_username_and_subreddit=MagicMock(return_value=None))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())
        monitored_sub = MonitoredSub(
            name='test_subreddit',
            high_volume_reposter_ban_user=False,
            high_volume_reposter_threshold=100,
            high_volume_reposter_notify_mod_mail=False,
            high_volume_reposter_remove_post=True
        )
        post = Post(subreddit='test_subreddit', author='test_user')
        sub_monitor.handle_high_volume_reposter_check(post, mock_uow, monitored_sub)
        mock_ban_user.assert_not_called()
        mock_remove_post.assert_called_once_with(monitored_sub, ANY)
        mock_response_handler.send_mod_mail.assert_not_called()

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_high_volume_reposter_check_over_threshold_remove_and_ban(self, mock_ban_user, mock_remove_post):
        mock_uow = MagicMock(
            stat_top_reposter=MagicMock(get_total_reposts_by_author_and_day_range=MagicMock(return_value=200)),
            user_whitelist=MagicMock(get_by_username_and_subreddit=MagicMock(return_value=None))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())
        monitored_sub = MonitoredSub(
            name='test_subreddit',
            high_volume_reposter_ban_user=True,
            high_volume_reposter_threshold=100,
            high_volume_reposter_notify_mod_mail=False,
            high_volume_reposter_remove_post=True
        )
        post = Post(subreddit='test_subreddit', author='test_user')
        sub_monitor.handle_high_volume_reposter_check(post, mock_uow, monitored_sub)
        mock_ban_user.assert_called_once_with('test_user', 'test_subreddit', 'High volume of reposts detected by Repost Sleuth')
        mock_remove_post.assert_called_once_with(monitored_sub, ANY)
        mock_response_handler.send_mod_mail.assert_not_called()

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_high_volume_reposter_check_over_threshold_send_mod_mail(self, mock_ban_user, mock_remove_post):
        mock_uow = MagicMock(
            stat_top_reposter=MagicMock(get_total_reposts_by_author_and_day_range=MagicMock(return_value=200)),
            user_whitelist=MagicMock(get_by_username_and_subreddit=MagicMock(return_value=None))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())
        monitored_sub = MonitoredSub(
            name='test_subreddit',
            high_volume_reposter_ban_user=False,
            high_volume_reposter_threshold=100,
            high_volume_reposter_notify_mod_mail=True,
            high_volume_reposter_remove_post=False
        )
        post = Post(subreddit='test_subreddit', author='test_user')
        sub_monitor.handle_high_volume_reposter_check(post, mock_uow, monitored_sub)
        mock_ban_user.assert_not_called()
        mock_remove_post.assert_not_called()
        mock_response_handler.send_mod_mail.assert_called_with(
            'test_subreddit', ANY, 'New Submission From High Volume Reposter', source='sub_monitor')

    @patch.object(SubMonitor, '_remove_post')
    @patch.object(SubMonitor, '_ban_user')
    def test__handle_high_volume_reposter_check_over_threshold_ignore_whitelist(self, mock_ban_user, mock_remove_post):
        user_whitelist = UserWhitelist(username='test_user', ignore_high_volume_repost_detection=True)
        mock_uow = MagicMock(
            stat_top_reposter=MagicMock(get_total_reposts_by_author_and_day_range=MagicMock(return_value=200)),
            user_whitelist=MagicMock(get_by_username_and_subreddit=MagicMock(return_value=user_whitelist))
        )
        mock_response_handler = Mock(send_mod_mail=Mock())
        sub_monitor = SubMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_response_handler,
                                 config=MagicMock())
        monitored_sub = MonitoredSub(
            name='test_subreddit',
            high_volume_reposter_ban_user=False,
            high_volume_reposter_threshold=100,
            high_volume_reposter_notify_mod_mail=True,
            high_volume_reposter_remove_post=False
        )
        post = Post(subreddit='test_subreddit', author='test_user')
        sub_monitor.handle_high_volume_reposter_check(post, mock_uow, monitored_sub)
        mock_ban_user.assert_not_called()
        mock_remove_post.assert_not_called()
        mock_response_handler.send_mod_mail.assert_not_called()