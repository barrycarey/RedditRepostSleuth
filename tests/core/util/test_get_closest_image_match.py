from unittest import TestCase

from redditrepostsleuth.core.model.search_results.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.util.repost_helpers import get_closest_image_match


class Test_Repost_Helpers(TestCase):
    def test_get_closest_image_match__return_closest(self):
        matches = []
        match1 = ImageSearchMatch()
        match2 = ImageSearchMatch()
        match3 = ImageSearchMatch()
        match1.hamming_match_percent = 98
        match2.hamming_match_percent = 80
        match3.hamming_match_percent = 85
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)

        r = get_closest_image_match(matches, check_url=False)
        self.assertEqual(r, match1)

    def test_get_closest_image_match__empty_list(self):
        matches = []
        r = get_closest_image_match(matches)
        self.assertIsNone(r)
