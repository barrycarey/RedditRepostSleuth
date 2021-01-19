import json
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import patch, Mock

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.util.repost_filters import cross_post_filter, same_sub_filter, annoy_distance_filter, \
    hamming_distance_filter, filter_newer_matches, filter_days_old_matches, filter_same_author, filter_same_post, \
    filter_title_keywords, filter_title_distance, filter_dead_urls_remote
from redditrepostsleuth.core.util.repost_helpers import filter_search_results
from tests.core.helpers import get_image_search_results_multi_match
from requests.exceptions import ConnectionError

class TestRepostFilters(TestCase):
    def test_cross_post_filter__remove_crosspost(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[1].post.crosspost_parent = 'abc'
        r = list(filter(cross_post_filter, search_results.matches))
        self.assertEqual(2, len(r))
        self.assertEqual(1, r[0].post.id)
        self.assertEqual(3, r[1].post.id)

    def test_same_sub_filter__remove_same_sub(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].post.subreddit = 'sub1'
        search_results.matches[1].post.subreddit = 'sub1'
        search_results.matches[2].post.subreddit = 'sub2'
        r = list(filter(same_sub_filter('sub2'), search_results.matches))
        self.assertEqual(1, len(r))
        self.assertEqual(3, r[0].post.id)

    def test_hamming_distance_filter__remove_higher_distance(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].hamming_distance = 10
        search_results.matches[1].hamming_distance = 20
        search_results.matches[2].hamming_distance = 25
        r = list(filter(hamming_distance_filter(11), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].post.id)

    def test_annoy_distance_filter__remove_higher_distance(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].annoy_distance = .100
        search_results.matches[1].annoy_distance = .200
        search_results.matches[2].annoy_distance = .250
        r = list(filter(annoy_distance_filter(0.150), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].post.id)


    def test_filter_days_old_matches__remove_older(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].post.created_at = datetime.utcfromtimestamp(1571349660)
        search_results.matches[1].post.created_at = datetime.utcfromtimestamp(1571090460)
        search_results.matches[2].post.created_at = datetime.utcfromtimestamp(1570917660)

        with patch('redditrepostsleuth.core.util.repost_filters.datetime') as mock_date:
            mock_date.utcnow.return_value = datetime.utcfromtimestamp(1571360460)
            r = list(filter(filter_days_old_matches(2), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].post.id)

    def test_filter_same_author__remove_same_author(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].post.author = 'barry'
        search_results.matches[1].post.author = 'barry'
        search_results.matches[2].post.author = 'steve'

        r = list(filter(filter_same_author('barry'), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].post.id)

    def test_filter_title_similarity__remove_lower(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].title_similarity = .500
        search_results.matches[1].title_similarity = .75
        search_results.matches[2].title_similarity = .80
        r = list(filter(filter_title_distance(.76), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].post.id)

    def test_filter_same_post__remove_same(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].post.post_id = '1111'
        search_results.matches[1].post.post_id = '2222'
        search_results.matches[2].post.post_id = '3333'
        r = list(filter(filter_same_post('3333'), search_results.matches))
        self.assertEqual(2, len(r))
        self.assertEqual(1, r[0].post.id)
        self.assertEqual(2, r[1].post.id)

    def test_filter_title_keywords(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].post.title = 'Some repost title'
        search_results.matches[1].post.title = 'This is a repost'
        search_results.matches[2].post.title = 'some normal title'
        r = list(filter(filter_title_keywords(['repost']), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].post.id)

    def test_filter_title_keywords_uppercase__remove_keyword(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].post.title = 'SOME REPOSTTITLE'
        search_results.matches[1].post.title = 'THIS IS A REPOST'
        search_results.matches[2].post.title = 'NORMAL TITLE'
        r = list(filter(filter_title_keywords(['repost']), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].post.id)

    def test_filter_search_results_hit_all_filters(self):
        search_results = get_image_search_results_multi_match()
        search_results.search_settings.filter_same_author = True
        search_results.search_settings.filter_crossposts = True
        search_results.search_settings.only_older_matches = True
        search_results.search_settings.same_sub = True
        search_results.search_settings.target_title_match = None
        search_results.search_settings.max_days_old = 4
        search_results.checked_post.author = 'barry'
        search_results.checked_post.subreddit = 'sub1'
        search_results.checked_post.post_id = '1111'
        search_results.checked_post.created_at = datetime.utcfromtimestamp(1573995250)
        matches = []
        # Dropped by same author
        matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(id=1, author='barry', post_id='abc123', created_at=datetime.strptime('2019-01-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        # Dropped by crosspost
        matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(id=2, author='steve', post_id='123abc', crosspost_parent='abc', created_at=datetime.strptime('2019-06-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        # Dropped by only older
        matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(id=3, author='steve', post_id='3333', title='some normal title', created_at=datetime.utcfromtimestamp(1574081650)),
                10,
                0.250,
                32
            )
        )
        # Dropped by same sub
        matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(id=4, author='steve', post_id='4444', title='some normal title', subreddit='sub2', created_at=datetime.utcfromtimestamp(1573908850)),
                10,
                0.250,
                32
            )
        )
        matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(id=5, author='steve', post_id='5555', title='some normal title', subreddit='sub1', created_at=datetime.utcfromtimestamp(1573988200)),
                10,
                0.250,
                32
            )
        )
        # Dropped by same post
        matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(id=6, post_id='1111', title='some normal title', subreddit='sub1', created_at=datetime.utcfromtimestamp(1573908850)),
                10,
                0.250,
                32
            )
        )
        matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(id=7, post_id='6666', title='some normal title', subreddit='sub1',
                     created_at=datetime.utcfromtimestamp(1573908850)),
                10,
                0.250,
                32
            )
        )
        search_results.matches = matches
        with patch('redditrepostsleuth.core.util.repost_filters.datetime') as mock_date:
            mock_date.utcnow.return_value = datetime.utcfromtimestamp(1574360460)
            r = filter_search_results(search_results)
        self.assertEqual(1, len(search_results.matches))
        self.assertEqual('5555', r.matches[0].post.post_id)
        print('')

    def test_filter_newer_matches__remove_newer(self):
        search_results = get_image_search_results_multi_match()
        search_results.matches[0].post.created_at = datetime.utcfromtimestamp(1574168050)
        search_results.matches[1].post.created_at = datetime.utcfromtimestamp(1574081650)
        search_results.matches[2].post.created_at = datetime.utcfromtimestamp(1573908850)
        r = list(filter(filter_newer_matches(datetime.utcfromtimestamp(1573995250)), search_results.matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].post.id)

    def test_filter_dead_urls_remote_connection_error(self):
        search_results = get_image_search_results_multi_match()
        with mock.patch('redditrepostsleuth.core.services.duplicateimageservice.requests.post') as mock_post:
            mock_post.side_effect = ConnectionError()
            r = filter_dead_urls_remote('test.com', search_results.matches)
            self.assertEqual(3, len(r))

    def test_filter_dead_urls_remote_bad_status_code(self):
        search_results = get_image_search_results_multi_match()
        with mock.patch('redditrepostsleuth.core.services.duplicateimageservice.requests.post') as mock_post:
            mock_post.return_value = Mock(status_code=500)
            r = filter_dead_urls_remote('test.com', search_results.matches)
            self.assertEqual(3, len(r))

    def test_filter_dead_urls_remote_bad_valid_res_remove_one(self):
        res = [
            {'id': '1111', 'action': 'remove'},
        ]
        search_results = get_image_search_results_multi_match()
        with mock.patch('redditrepostsleuth.core.util.helpers.requests.post') as mock_post:
            mock_post.return_value = Mock(status_code=200, text=json.dumps(res))
            r = filter_dead_urls_remote('test.com', search_results.matches)
            self.assertEqual(2, len(r))
            self.assertEqual('2222', r[0].post.post_id)
            self.assertEqual('3333', r[1].post.post_id)