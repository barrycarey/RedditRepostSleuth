from unittest import TestCase
from datetime import datetime
from unittest.mock import patch, MagicMock, Mock

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate, MonitoredSub
from redditrepostsleuth.core.model.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.search_results.image_search_match import ImageSearchMatch

from redditrepostsleuth.core.util.helpers import chunk_list, searched_post_str, create_first_seen, \
    post_type_from_url, build_msg_values_from_search, build_image_msg_values_from_search, \
    get_image_search_settings_for_monitored_sub, get_default_image_search_settings, build_site_search_url


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

    def test_first_seen_valid_input(self):
        post = Post(subreddit='somesub', post_id='1234', created_at=datetime.fromtimestamp(1572799193))
        r = create_first_seen(post, 'somesub')
        expected = f'First seen [Here](https://redd.it/1234) on {post.created_at.strftime("%Y-%m-%d")}'
        self.assertEqual(expected, r)

    def test_first_seen_no_link_sub_valid_input(self):
        post = Post(subreddit='somesub', post_id='1234', created_at=datetime.fromtimestamp(1572799193))
        r = create_first_seen(post, 'natureismetal')
        expected = f'First seen in somesub on {post.created_at.strftime("%Y-%m-%d")}'
        self.assertEqual(expected, r)


    def test_post_type_from_url_image_lowercase(self):
        self.assertEqual('image', post_type_from_url('www.example.com/test.jpg'))

    def test_post_type_from_url_image_uppercase(self):
        self.assertEqual('image', post_type_from_url('www.example.com/test.Jpg'))

    def test_build_image_msg_values_from_search_include_meme_template(self):
        match1 = ImageSearchMatch(
            'test.com',
            111,
            Post(url='www.example.com',
                 created_at=datetime.fromtimestamp(1572799193),
                 post_id='1234',
                 subreddit='somesub')
            ,
            3,
            1.0,
            32
        )

        wrapper = ImageSearchResults('test.com', Mock())
        wrapper.search_times = ImageSearchTimes()
        wrapper.search_times.total_search_time = 1
        wrapper.matches.append(match1)
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(subreddit='sub2')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        wrapper.meme_template = MemeTemplate(id=10)
        result = build_image_msg_values_from_search(wrapper)
        self.assertIn('meme_template_id', result)
        self.assertEqual(10, result['meme_template_id'])

    def test_build_image_msg_values_from_search_include_false_positive_data(self):
        match1 = ImageSearchMatch(
            'test.com',
            111,
            Post(url='www.example.com',
                 created_at=datetime.fromtimestamp(1572799193),
                 post_id='1234',
                 subreddit='somesub')
            ,
            3,
            1.0,
            32
        )

        wrapper = ImageSearchResults('test.com', Mock())
        wrapper.search_times = ImageSearchTimes()
        wrapper.search_times.total_search_time = 1
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(post_id='1234')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        wrapper.meme_template = MemeTemplate(id=10)
        result = build_image_msg_values_from_search(wrapper)
        self.assertIn('false_positive_data', result)
        self.assertEqual('{"post_id": "1234", "meme_template": 10}', result['false_positive_data'])

    def test_build_image_msg_values_from_search_correct_match_percent(self):
        match1 = ImageSearchMatch(
            'test.com',
            111,
            Post(url='www.example.com',
                 created_at=datetime.fromtimestamp(1572799193),
                 post_id='1234',
                 subreddit='somesub')
            ,
            3,
            1.0,
            32
        )

        wrapper = ImageSearchResults('test.com', Mock())
        wrapper.search_times = ImageSearchTimes()
        wrapper.search_times.total_search_time = 1
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(post_id='1234')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        wrapper.meme_template = MemeTemplate(id=10)
        result = build_image_msg_values_from_search(wrapper)
        self.assertEqual('90.62%', result['newest_percent_match'])

    def test_build_msg_values_from_search_key_total(self):
        match1 = ImageSearchMatch(
            'test.com',
            111,
            Post(),
            1,
            1.0,
            32
        )
        match1.post = Post(url='www.example.com',
                           created_at=datetime.fromtimestamp(1572799193),
                           post_id='1234',
                           subreddit='somesub')
        wrapper = ImageSearchResults('test.com', Mock())
        wrapper.search_times = ImageSearchTimes()
        wrapper.search_times.total_search_time = 1
        wrapper.matches.append(match1)
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(subreddit='sub2')

        result = build_msg_values_from_search(wrapper)

        self.assertEqual(20, len(result.keys()))
        # TODO - Maybe test return values.  Probably not needed

    def test_build_msg_values_from_search_no_match_key_total(self):
        wrapper = ImageSearchResults('test.com', Mock())
        wrapper.search_times = ImageSearchTimes()
        wrapper.search_times.total_search_time = 1
        wrapper.checked_post = Post(subreddit='sub2', post_id='abc', author='test')
        result = build_msg_values_from_search(wrapper)

        self.assertEqual(10, len(result.keys()))

    def test_build_msg_values_from_search_no_match_custom_key_total(self):
        wrapper = ImageSearchResults('test.com', Mock())
        wrapper.search_times = ImageSearchTimes()
        wrapper.search_times.total_search_time = 1
        wrapper.checked_post = Post(subreddit='sub2', post_id='abc', author='test')
        result = build_msg_values_from_search(wrapper, test1='test')

        self.assertEqual(11, len(result.keys()))

    def test_build_msg_values_from_search_extra_values(self):

        wrapper = ImageSearchResults('test.com', Mock())
        wrapper.search_times = ImageSearchTimes()
        wrapper.search_times.total_search_time = 1
        wrapper.checked_post = Post(subreddit='sub2', post_id='abc', author='test')

        result = build_msg_values_from_search(wrapper, item1='value1', item2='value2')

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
        self.assertEqual(75, r.max_matches)
        self.assertTrue(r.same_sub)
        self.assertEqual(44, r.max_days_old)
        self.assertFalse(r.filter_same_author)
        self.assertFalse(r.filter_crossposts)

    def test_get_default_image_search_settings(self):
        config = Config(
            target_image_match=55,
            target_image_meme_match=22,
            summons_meme_filter=True,
            summons_same_sub=True,
            summons_max_age=77,
            default_annoy_distance=.177
        )
        r = get_default_image_search_settings(config)
        self.assertEqual(55, r.target_match_percent)
        self.assertEqual(22, r.target_meme_match_percent)
        self.assertTrue(r.meme_filter)
        self.assertIsNone(r.target_title_match)
        self.assertEqual(75, r.max_matches)
        self.assertTrue(r.same_sub)
        self.assertEqual(77, r.max_days_old)
        self.assertTrue(r.filter_same_author)
        self.assertTrue(r.filter_crossposts)
        self.assertEqual(.177, r.target_annoy_distance)

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
        expected = 'https://www.repostsleuth.com?postId=abc123&sameSub=true&filterOnlyOlder=true&memeFilter=true&filterDeadMatches=true&targetImageMatch=90&targetImageMemeMatch=95'
        self.assertEqual(expected, r)