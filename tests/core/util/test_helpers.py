import json
from unittest import TestCase, mock
from datetime import datetime
from unittest.mock import Mock
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate, MonitoredSub
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.model.search_settings import SearchSettings

from redditrepostsleuth.core.util.helpers import chunk_list, searched_post_str, \
    post_type_from_url, build_msg_values_from_search, build_image_msg_values_from_search, \
    get_image_search_settings_for_monitored_sub, get_default_image_search_settings, build_site_search_url, \
    build_image_report_link, get_default_link_search_settings, batch_check_urls, reddit_post_id_from_url, is_image_url, \
    base36encode, base36decode, get_next_ids, build_ingest_query_params


class TestHelpers(TestCase):

    def test_chunklist(self):
        l = list(range(15))
        chunks = list(chunk_list(l, 5))
        self.assertEqual(len(chunks), 3)

    def test_searched_post_str_valid_count(self):
        post = Post(post_type='image')
        r = searched_post_str(post, 10)
        expected = '**Searched Images:** 10'
        self.assertEqual(expected, r)

    def test_searched_post_str_link_valid_count(self):
        post = Post(post_type='link')
        r = searched_post_str(post, 10)
        expected = '**Searched Links:** 10'
        self.assertEqual(expected, r)

    def test_searched_post_str_unknowntype_valid_count(self):
        post = Post(post_type='video')
        r = searched_post_str(post, 10)
        expected = '**Searched:** 10'
        self.assertEqual(expected, r)

    def test_searched_post_str_formatting(self):
        post = Post(post_type='image')
        r = searched_post_str(post, 1000000)
        expected = '**Searched Images:** 1,000,000'
        self.assertEqual(expected, r)


    def test_post_type_from_url_image_lowercase(self):
        self.assertEqual('image', post_type_from_url('www.example.com/test.jpg'))

    def test_post_type_from_url_image_uppercase(self):
        self.assertEqual('image', post_type_from_url('www.example.com/test.Jpg'))

    def test_build_image_msg_values_from_search_include_meme_template(self):
        search_results = self._get_image_search_results_one_match()
        search_results.matches[0].hamming_distance = 3
        search_results.meme_template = MemeTemplate(id=10)
        result = build_image_msg_values_from_search(search_results)
        self.assertIn('meme_template_id', result)
        self.assertEqual(10, result['meme_template_id'])

    def test_build_image_msg_values_from_search_correct_match_percent(self):
        search_results = self._get_image_search_results_one_match()
        search_results.matches[0].hamming_distance = 3
        result = build_image_msg_values_from_search(search_results)
        self.assertEqual('90.62%', result['newest_percent_match'])

    def test_build_msg_values_from_search_key_total(self):
        search_results = self._get_image_search_results_one_match()
        result = build_msg_values_from_search(search_results)
        self.assertEqual(37, len(result.keys()))
        # TODO - Maybe test return values.  Probably not needed

    def test_build_msg_values_from_search_no_match_key_total(self):
        search_results = self._get_image_search_results_no_match()
        result = build_msg_values_from_search(search_results)
        self.assertEqual(27, len(result.keys()))

    def test_build_msg_values_from_search_no_match_custom_key_total(self):
        search_results = self._get_image_search_results_no_match()
        result = build_msg_values_from_search(search_results, test1='test')
        self.assertEqual(28, len(result.keys()))

    def test_build_msg_values_from_search_extra_values(self):

        seach_results = self._get_image_search_results_one_match()
        result = build_msg_values_from_search(seach_results, item1='value1', item2='value2')
        self.assertTrue('item1' in result)
        self.assertTrue('item2' in result)
        self.assertEqual(result['item1'], 'value1')
        self.assertEqual(result['item2'], 'value2')

    def test_get_image_search_settings_for_monitored_sub(self):
        monitored_sub = MonitoredSub(
            target_image_match=51,
            target_image_meme_match=66,
            meme_filter=True,
            target_title_match=88,
            check_title_similarity=True,
            same_sub_only=True,
            target_days_old=44,
            filter_same_author=False,
            filter_crossposts=False
        )
        r = get_image_search_settings_for_monitored_sub(monitored_sub, target_annoy_distance=170.0)
        self.assertEqual(51, r.target_match_percent)
        self.assertEqual(66, r.target_meme_match_percent)
        self.assertTrue(r.meme_filter)
        self.assertEqual(88, r.target_title_match)
        self.assertEqual(200, r.max_matches)
        self.assertTrue(r.same_sub)
        self.assertEqual(44, r.max_days_old)
        self.assertFalse(r.filter_same_author)
        self.assertFalse(r.filter_crossposts)

    def test_get_default_image_search_settings(self):
        config = Config(
            default_image_target_match=55,
            default_image_target_meme_match=99,
            default_image_target_title_match=99,
            default_image_dead_matches_filter=True,
            default_image_removed_match_filter=True,
            default_image_only_older_matches=True,
            default_image_same_author_filter=True,
            default_image_crosspost_filter=True,
            default_image_meme_filter=True,
            default_image_same_sub_filter=True,
            default_image_max_days_old_filter=180,
            default_image_target_annoy_distance=.177,
            default_image_max_matches=250

        )
        r = get_default_image_search_settings(config)
        self.assertEqual(55, r.target_match_percent)
        self.assertEqual(99, r.target_meme_match_percent)
        self.assertEqual(99, r.target_title_match)
        self.assertTrue(r.filter_dead_matches)
        self.assertTrue(r.filter_removed_matches)
        self.assertTrue(r.only_older_matches)
        self.assertTrue(r.filter_same_author)
        self.assertTrue(r.filter_crossposts)
        self.assertTrue(r.meme_filter)
        self.assertTrue(r.same_sub)
        self.assertEqual(180, r.max_days_old)
        self.assertEqual(.177, r.target_annoy_distance)
        self.assertEqual(250, r.max_matches)

    def test_get_default_link_search_settings(self):
        config = Config(
            default_link_target_title_match=99,
            default_link_dead_matches_filter=True,
            default_link_removed_match_filter=True,
            default_link_only_older_matches=True,
            default_link_same_author_filter=True,
            default_link_crosspost_filter=True,
            default_link_same_sub_filter=True,
            default_link_max_days_old_filter=180,

        )
        r = get_default_link_search_settings(config)
        self.assertEqual(99, r.target_title_match)
        self.assertTrue(r.filter_dead_matches)
        self.assertTrue(r.filter_removed_matches)
        self.assertTrue(r.only_older_matches)
        self.assertTrue(r.filter_same_author)
        self.assertTrue(r.filter_crossposts)
        self.assertTrue(r.same_sub)
        self.assertEqual(180, r.max_days_old)
        self.assertEqual(75, r.max_matches)


    def test_build_site_search_url_no_search_settings(self):
        self.assertIsNone(build_site_search_url('123', None))

    def test_test_build_site_search_url(self):
        search_settings = ImageSearchSettings(
            90,
            170,
            same_sub=True,
            only_older_matches=True,
            meme_filter=True,
            filter_dead_matches=True,
            target_meme_match_percent=95
        )
        r = build_site_search_url('abc123', search_settings)
        expected = 'https://www.repostsleuth.com/search?postId=abc123&sameSub=true&filterOnlyOlder=true&memeFilter=true&filterDeadMatches=true&targetImageMatch=90&targetImageMemeMatch=95'
        self.assertEqual(expected, r)

    def test_build_image_report_link_negative(self):
        search_results = ImageSearchResults('test.com', Mock(), checked_post=Post(post_id='abc123'))
        result = build_image_report_link(search_results)
        expected = "*I'm not perfect, but you can help. Report [ [False Negative](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20Negative&message={\"post_id\": \"abc123\", \"meme_template\": null}) ]*"
        self.assertEqual(expected, result)

    def test_build_image_report_link_positive(self):
        search_results = ImageSearchResults('test.com', Mock(), checked_post=Post(post_id='abc123'))
        search_results.matches.append(ImageSearchMatch('test.com', 123, Mock(), 1, 1, 32))
        result = build_image_report_link(search_results)
        expected = "*I'm not perfect, but you can help. Report [ [False Positive](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20Positive&message={\"post_id\": \"abc123\", \"meme_template\": null}) ]*"
        self.assertEqual(expected, result)


    def test_batch_check_urls_valid_call(self):
        urls = [
            {'url': 'example.com', 'id': '1'},
            {'url': 'example.com', 'id': '2'},
            {'url': 'example.com', 'id': '3'},
            {'url': 'example.com', 'id': '4'},
            {'url': 'example.com', 'id': '5'},
        ]

        api_return = [
            {'url': 'example.com', 'id': '1', 'action': 'remove'},
            {'url': 'example.com', 'id': '2', 'action': 'update'},
            {'url': 'example.com', 'id': '3', 'action': 'update'},
            {'url': 'example.com', 'id': '4', 'action': 'remove'},
            {'url': 'example.com', 'id': '5', 'action': 'update'},
        ]

        with mock.patch('redditrepostsleuth.core.util.helpers.requests.post') as mock_post:
            mock_post.return_value = Mock(status_code=200, text=json.dumps(api_return))
            res = batch_check_urls(urls, 'test.com')

        self.assertEqual(3, len(res))
        self.assertEqual('2', res[0]['id'])
        self.assertEqual('3', res[1]['id'])
        self.assertEqual('5', res[2]['id'])

    def test_batch_check_urls_valid_call_none_removed(self):
        urls = [
            {'url': 'example.com', 'id': '1'},
            {'url': 'example.com', 'id': '2'},
            {'url': 'example.com', 'id': '3'},
            {'url': 'example.com', 'id': '4'},
            {'url': 'example.com', 'id': '5'},
        ]

        api_return = [
            {'url': 'example.com', 'id': '1', 'action': 'update'},
            {'url': 'example.com', 'id': '2', 'action': 'update'},
            {'url': 'example.com', 'id': '3', 'action': 'update'},
            {'url': 'example.com', 'id': '4', 'action': 'update'},
            {'url': 'example.com', 'id': '5', 'action': 'update'},
        ]

        with mock.patch('redditrepostsleuth.core.util.helpers.requests.post') as mock_post:
            mock_post.return_value = Mock(status_code=200, text=json.dumps(api_return))
            res = batch_check_urls(urls, 'test.com')

        self.assertEqual(5, len(res))

    def test_batch_check_urls_valid_bad_status(self):
        urls = [
            {'url': 'example.com', 'id': '1'},
            {'url': 'example.com', 'id': '2'},
            {'url': 'example.com', 'id': '3'},
            {'url': 'example.com', 'id': '4'},
            {'url': 'example.com', 'id': '5'},
        ]

        with mock.patch('redditrepostsleuth.core.util.helpers.requests.post') as mock_post:
            mock_post.return_value = Mock(status_code=500, text=json.dumps(urls))
            res = batch_check_urls(urls, 'test.com')

        self.assertEqual(5, len(res))

    def test_batch_check_urls_valid_bad_connection_error(self):
        urls = [
            {'url': 'example.com', 'id': '1'},
            {'url': 'example.com', 'id': '2'},
            {'url': 'example.com', 'id': '3'},
            {'url': 'example.com', 'id': '4'},
            {'url': 'example.com', 'id': '5'},
        ]

        with mock.patch('redditrepostsleuth.core.util.helpers.requests.post') as mock_post:
            mock_post.side_effect = ConnectionError()
            res = batch_check_urls(urls, 'test.com')

        self.assertEqual(5, len(res))


    def test_reddit_post_id_from_url_long_url_return_post_id(self):
        url = 'https://www.reddit.com/r/memes/comments/ln0sj7/you_guys_are_amazing_by_the_way/'
        self.assertEqual('ln0sj7', reddit_post_id_from_url(url))

    def test_reddit_post_id_from_url_short_url_return_post_id(self):
        url = 'https://redd.it/ln0sj7'
        self.assertEqual('ln0sj7', reddit_post_id_from_url(url))

    def test_reddit_post_id_from_url_invalid_url_return_none(self):
        url = 'https://somerandomdomain/ln0sj7'
        self.assertIsNone(reddit_post_id_from_url(url))

    def test_reddit_post_id_from_url_no_url_return_none(self):
        self.assertIsNone(reddit_post_id_from_url(None))

    def test_is_image_url_valid_url_return_true(self):
        url = 'https://example.com/someimage.png'
        self.assertTrue(is_image_url(url))

    def test_is_image_url_invalid_url_return_false(self):
        url = 'https://exxample.com/somerandompage'
        self.assertFalse(is_image_url(url))

    def test_is_image_url_invalid_image_type_return_false(self):
        url = 'https://example.com/someimage.bmp'
        self.assertFalse(is_image_url(url))

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

    def test_base36decode_valid_int(self):
        self.assertEqual(1546791610, base36decode('pkx41m'))

    def test_base36decode_invalid_value(self):
        with self.assertRaises(TypeError):
            self.assertEqual(1546791610, base36decode(111111))

    def test_base36encode_valid_int(self):
        self.assertEqual('pkx41m', base36encode(1546791610))

    def test_base36decode_invalid_value(self):
        with self.assertRaises(TypeError):
            self.assertEqual(1546791610, base36encode('pkx41m'))

    def test_get_next_ids_valid_values(self):
        expected = [
            't3_pkx41m',
            't3_pkx41n',
            't3_pkx41o',
            't3_pkx41p',
            't3_pkx41q'

        ]
        self.assertListEqual(expected, get_next_ids('pkx41m', 5)[0])

    def test_get_next_ids_invalid_id(self):
        with self.assertRaises(TypeError):
            get_next_ids(1111, 5)

    def test_build_ingest_query_params(self):
        expected = {'submission_ids': 't3_pmfkfs,t3_pmfkft,t3_pmfkfu,t3_pmfkfv,t3_pmfkfw'}
        print(build_ingest_query_params('pmfkfs', limit=5))
        self.assertDictEqual(expected, build_ingest_query_params('pmfkfs', limit=5))