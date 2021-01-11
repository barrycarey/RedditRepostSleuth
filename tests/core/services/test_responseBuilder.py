import json
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import MagicMock, Mock

from redditrepostsleuth.core.db.databasemodels import MonitoredSub, Post
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.model.search_settings import SearchSettings
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from tests.core.services.response_builder_expected_responses import IMAGE_OC_NO_CLOSE_NO_SIG_NO_STATS_NO_SEARCH, \
    IMAGE_OC_ONLY_SIGNATURE, IMAGE_OC_ONLY_STATUS, IMAGE_OC_LINK_ONLY, IMAGE_OC_ONLY_SEARCH_SETTINGS, \
    IMAGE_OC_ALL_ENABLED, IMAGE_REPOST_ONE_MATCH_ALL_ENABLED, IMAGE_REPOST_MULTI_MATCH_ALL_ENABLED, \
    IMAGE_OC_ALL_ENABLED_ALL_ENABLED_NO_MEME, IMAGE_REPOST_SUBREDDIT_CUSTOM, IMAGE_OC_SUBREDDIT_CUSTOM, \
    LINK_OC_ALL_ENABLED, LINK_REPOST_ALL_ENABLED


class TestResponseBuilder(TestCase):

    def test_build_default_comment__image_oc_all_enabled(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        result = response_builder.build_default_comment(search_results, signature=True, stats=True, search_link=True,
                                                        search_settings=True)
        self.assertEqual(IMAGE_OC_ALL_ENABLED, result)

    def test_build_default_comment__image_oc_all_enabled_close_match(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        search_results.closest_match = ImageSearchMatch('test.com', 1, Post(post_id='abc123',
                                                                            created_at=datetime.strptime(
                                                                                '2019-01-28 05:20:03',
                                                                                '%Y-%m-%d %H:%M:%S')), 5, 3, 32)
        result = response_builder.build_default_comment(search_results, signature=True, stats=True, search_link=True,
                                                        search_settings=True)
        self.assertEqual(IMAGE_OC_ALL_ENABLED_ALL_ENABLED_NO_MEME, result)

    def test_build_default_comment__image_oc_no_sig_or_stat_or_search_link(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        result = response_builder.build_default_comment(search_results, signature=False, stats=False, search_link=False,
                                                        search_settings=False)
        self.assertEqual(IMAGE_OC_NO_CLOSE_NO_SIG_NO_STATS_NO_SEARCH, result)

    def test_build_default_comment__image_oc_only_signature(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        result = response_builder.build_default_comment(search_results, signature=True, stats=False, search_link=False,
                                                        search_settings=False)
        self.assertEqual(IMAGE_OC_ONLY_SIGNATURE, result)

    def test_build_default_comment__image_oc_only_stats(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        result = response_builder.build_default_comment(search_results, signature=False, stats=True, search_link=False,
                                                        search_settings=False)
        self.assertEqual(IMAGE_OC_ONLY_STATUS, result)

    def test_build_default_comment__image_oc_only_search_link(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        result = response_builder.build_default_comment(search_results, signature=False, stats=False, search_link=True,
                                                        search_settings=False)
        self.assertEqual(IMAGE_OC_LINK_ONLY, result)

    def test_build_default_comment__image_oc_only_search_settingsk(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        result = response_builder.build_default_comment(search_results, signature=False, stats=False, search_link=False,
                                                        search_settings=True)
        self.assertEqual(IMAGE_OC_ONLY_SEARCH_SETTINGS, result)

    def test_build_default_comment__image_repost_one_match_all_enabled(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_one_match()
        result = response_builder.build_default_comment(search_results, signature=True, stats=True, search_link=True,
                                                        search_settings=True)
        self.assertEqual(IMAGE_REPOST_ONE_MATCH_ALL_ENABLED, result)

    def test_build_default_comment__image_repost_multi_match_all_enabled(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_multi_match()
        result = response_builder.build_default_comment(search_results, signature=True, stats=True, search_link=True,
                                                        search_settings=True)
        self.assertEqual(IMAGE_REPOST_MULTI_MATCH_ALL_ENABLED, result)

    def test_build_sub_comment__image_repost_all_enabled(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_multi_match()
        result = response_builder.build_sub_comment(self._get_monitored_sub(), search_results, signature=True,
                                                    stats=True, search_link=True,
                                                    search_settings=True)
        self.assertEqual(IMAGE_REPOST_SUBREDDIT_CUSTOM, result)

    def test_build_sub_comment__image_oc_all_enabled(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_image_search_results_no_match()
        result = response_builder.build_sub_comment(self._get_monitored_sub(), search_results, signature=True,
                                                    stats=True, search_link=True,
                                                    search_settings=True)
        self.assertEqual(IMAGE_OC_SUBREDDIT_CUSTOM, result)

    def test_build_default_comment__link_oc_all_enabled(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_link_search_results_no_match()
        result = response_builder.build_default_comment(search_results, signature=True,
                                                        stats=True, search_link=True,
                                                        search_settings=True)
        self.assertEqual(LINK_OC_ALL_ENABLED, result)

    def test_build_default_comment__link_repost_all_enabled(self):
        response_builder = ResponseBuilder(MagicMock())
        search_results = self._get_link_search_results_matches_match()
        result = response_builder.build_default_comment(search_results, signature=True,
                                                        stats=True, search_link=True,
                                                        search_settings=True)
        self.assertEqual(LINK_REPOST_ALL_ENABLED, result)

    def _get_image_search_settings(self):
        return ImageSearchSettings(
            90,
            .077,
            target_meme_match_percent=50,
            meme_filter=False,
            max_depth=5000,
            target_title_match=None,
            max_matches=75,
            same_sub=False,
            max_days_old=190,
            filter_dead_matches=True,
            filter_removed_matches=True,
            only_older_matches=True,
            filter_same_author=True,
            filter_crossposts=True
        )

    def _get_search_settings(self):
        return SearchSettings(
            target_title_match=None,
            max_matches=75,
            same_sub=False,
            max_days_old=190,
            filter_dead_matches=True,
            filter_removed_matches=True,
            only_older_matches=True,
            filter_same_author=True,
            filter_crossposts=True
        )

    def _get_image_search_results_no_match(self):
        search_results = ImageSearchResults('test.com', self._get_image_search_settings(),
                                            checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
        search_results.search_times = ImageSearchTimes()
        search_results.search_times.total_search_time = 10
        return search_results

    def _get_image_search_results_one_match(self):
        search_results = ImageSearchResults('test.com', self._get_image_search_settings(),
                                            checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
        search_results.search_times = ImageSearchTimes()
        search_results.search_times.total_search_time = 10
        search_results.matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(post_id='abc123', created_at=datetime.strptime('2019-01-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        return search_results

    def _get_image_search_results_multi_match(self):
        search_results = ImageSearchResults('test.com', self._get_image_search_settings(),
                                            checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
        search_results.search_times = ImageSearchTimes()
        search_results.search_times.total_search_time = 10
        search_results.matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(post_id='abc123', created_at=datetime.strptime('2019-01-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        search_results.matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(post_id='123abc', created_at=datetime.strptime('2019-06-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        return search_results

    def _get_link_search_results_no_match(self):
        search_times = ImageSearchTimes()
        search_times.total_search_time = 10
        return SearchResults(
            'test.com',
            self._get_search_settings(),
            checked_post=Post(post_id='abc123', post_type='link', subreddit='test'),
            search_times=search_times
        )

    def _get_link_search_results_matches_match(self):
        search_times = ImageSearchTimes()
        search_times.total_search_time = 10
        search_results = SearchResults(
            'test.com',
            self._get_search_settings(),
            checked_post=Post(post_id='abc123', post_type='link', subreddit='test'),
            search_times=search_times
        )
        search_results.matches.append(
            SearchMatch(
                'test.com',
                Post(post_id='123abc', created_at=datetime.strptime('2019-06-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
            )
        )

        return search_results

    def _get_monitored_sub(self):
        return MonitoredSub(
            repost_response_template='This is a custom repost template. {match_count} matches',
            oc_response_template='This is a custom OC template. Random Sub {this_subreddit}'
        )
