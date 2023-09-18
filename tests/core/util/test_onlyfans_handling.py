import json
from unittest import TestCase
from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError

from redditrepostsleuth.core.exception import UtilApiException
from redditrepostsleuth.core.util.onlyfans_handling import check_links_for_flagged_domains, \
    check_links_for_landing_pages, check_page_source_for_flagged_words, process_landing_link, get_profile_links


class TestOnlyfansHandling(TestCase):
    def test_check_links_for_flagged_domains_non_flagged_return_none(self):
        self.assertIsNone(check_links_for_flagged_domains(['google.com']))
    def test_check_links_for_flagged_domains_flagged_return_domain(self):
        self.assertEqual('onlyfans.com', check_links_for_flagged_domains(['onlyfans.com']))
    def test_check_links_for_flagged_domains_multi_flagged_return_first_domain(self):
        self.assertEqual('onlyfans.com', check_links_for_flagged_domains(['onlyfans.com', 'fansly.com']))
    def test_check_profile_links_for_landing_pages_non_landing_return_none(self):
        self.assertIsNone(check_links_for_landing_pages(['google.com']))
    def test_check_profile_links_for_landing_pages_valid_landing_return_url(self):
        self.assertEqual('linktr.ee/test', check_links_for_landing_pages(['linktr.ee/test']))
    def test_check_page_source_for_flagged_words_no_links_return_none(self):
        source = '<html><title>Test</title><body><a href="https://google.com">some link</a></body></html>'
        self.assertIsNone(check_page_source_for_flagged_words(source))
    def test_check_page_source_for_flagged_words_onlyfans_links_return_domain(self):
        source = '<html><title>Test</title><body><a href="https://onlyfans.com">some link</a></body></html>'
        self.assertEqual('onlyfans.com', check_page_source_for_flagged_words(source))
    @patch('redditrepostsleuth.core.util.onlyfans_handling.requests.get')
    def test_process_landing_link_invalid_response_status_raise(self, mock_requests):
        mock_requests.return_value = Mock(status_code=500)
        with self.assertRaises(UtilApiException):
            process_landing_link('test.com')
    @patch('redditrepostsleuth.core.util.onlyfans_handling.requests.get')
    def test_process_landing_link_fetch_source_and_flag(self, mock_requests):
        source = '<html><title>Test</title><body><a href="https://onlyfans.com">some link</a></body></html>'
        mock_requests.return_value = Mock(text=source, status_code=200)
        self.assertEqual('onlyfans.com', process_landing_link('test.com'))

    @patch('redditrepostsleuth.core.util.onlyfans_handling.requests.get')
    def test_get_profile_links_api_connect_fail(self, mock_requests):
        mock_requests.side_effect = ConnectionError()
        with self.assertRaises(UtilApiException):
            get_profile_links('testuser')

    @patch('redditrepostsleuth.core.util.onlyfans_handling.requests.get')
    def test_get_profile_links_api_bad_status(self, mock_requests):
        mock_requests.return_value = Mock(status_code=500)
        with self.assertRaises(UtilApiException):
            get_profile_links('testuser')
    @patch('redditrepostsleuth.core.util.onlyfans_handling.requests.get')
    def test_get_profile_links_get_links(self, mock_requests):
        expected = ['facebook.com', 'google.com']
        mock_requests.return_value = Mock(status_code=200, text=json.dumps(expected))
        self.assertListEqual(expected, get_profile_links('testuser'))