from unittest import TestCase

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.util.repost_helpers import get_closest_image_match


class Test_Repost_Helpers(TestCase):
    def test_get_closest_image_match__return_closest(self):
        matches = []
        match1 = ImageSearchMatch('test.com', 1, Post(id=1), 3, .077, 32)
        match2 = ImageSearchMatch('test.com', 1, Post(id=2), 5, .077, 32)
        match3 = ImageSearchMatch('test.com', 1, Post(id=3), 7, .077, 32)
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)

        r = get_closest_image_match(matches, validate_url=False)
        self.assertEqual(r, match1)

    def test_get_closest_image_match__empty_list(self):
        matches = []
        r = get_closest_image_match(matches)
        self.assertIsNone(r)
