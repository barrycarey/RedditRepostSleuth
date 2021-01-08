from unittest import TestCase, mock
from unittest.mock import Mock

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from datetime import datetime

from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.util.repost_helpers import sort_reposts, get_first_active_match, get_closest_image_match


class TestHelpers(TestCase):

    def test_sort_reposts_correct_order(self):
        match1 = RepostMatch()
        match2 = RepostMatch()
        match3 = RepostMatch()
        post1 = Post(id=1, created_at=datetime.fromtimestamp(1575508228))
        post2 = Post(id=2, created_at=datetime.fromtimestamp(1572916228))
        post3 = Post(id=3, created_at=datetime.fromtimestamp(1570237828))
        match1.post = post1
        match2.post = post2
        match3.post = post3
        matches = [match1, match2, match3]

        result = sort_reposts(matches)

        self.assertEqual(3, result[0].post.id)

    def test_get_first_active_match(self):
        def get_dummy_res(url, **kwargs):
            if url == 'www.bad.com':
                return Mock(status_code=400)
            else:
                return Mock(status_code=200)
        with mock.patch('redditrepostsleuth.core.util.repost_helpers.requests.head') as mock_head:
            mock_head.side_effect = get_dummy_res
            matches = [
                SearchMatch('www.dummy.com', Post(id=1, url='www.bad.com')),
                SearchMatch('www.dummy.com', Post(id=2, url='www.bad.com')),
                SearchMatch('www.dummy.com', Post(id=3, url='www.good.com')),
                SearchMatch('www.dummy.com', Post(id=4, url='www.good.com')),
            ]
            r = get_first_active_match(matches)
            self.assertEqual(3, r.post.id)

    def test_get_closest_image_match(self):
            matches = [
                ImageSearchMatch('www.dummy.com', 1, Post(id=1, url='www.bad.com'), hamming_distance=2),
                ImageSearchMatch('www.dummy.com', 1, Post(id=2, url='www.bad.com'), hamming_distance=98),
                ImageSearchMatch('www.dummy.com', 1, Post(id=3, url='www.good.com'), hamming_distance=25),
                ImageSearchMatch('www.dummy.com', 1, Post(id=4, url='www.good.com'), hamming_distance=24),
            ]
            r = get_closest_image_match(matches, check_url=False)
            self.assertEqual(2, r.post.id)