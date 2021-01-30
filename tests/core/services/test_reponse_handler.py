from unittest import TestCase
from unittest.mock import Mock

from redditrepostsleuth.core.services.response_handler import ResponseHandler


class TestResponseHandler(TestCase):

    def test_send_mod_mail_invalid_subreddit(self):
        subreddit_mock = Mock(return_value=None)
        reddit_mock = Mock(
            subreddit=subreddit_mock
        )
        response_handler = ResponseHandler(
            reddit_mock,
            Mock(),
            Mock(),
            Mock()
        )
        response_handler.send_mod_mail('test', 'test', 'test')
        subreddit_mock.assert_called()

    def test_send_mod_mail_valid_subreddit(self):
        message_mock = Mock(return_value=None)
        subreddit_mock = Mock(message=message_mock)
        get_subreddit = Mock(return_value=subreddit_mock)
        reddit_mock = Mock(
            subreddit=get_subreddit
        )
        response_handler = ResponseHandler(
            reddit_mock,
            Mock(),
            Mock(),
            Mock()
        )
        response_handler._save_private_message = Mock(return_value=None)
        response_handler.send_mod_mail('test subreddit', 'test subject', 'test body')
        get_subreddit.assert_called_with('test subreddit')
        message_mock.assert_called_with('test subject', 'test body')
        response_handler._save_private_message.assert_called()

