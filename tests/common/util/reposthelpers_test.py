from unittest import TestCase

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from redditrepostsleuth.core.util.reposthelpers import filter_matching_images


class TestRepostHelpers(TestCase):
    def test_filter_matching_images_crosspost(self):
        match = RepostMatch
        match.post = Post(crosspost_parent='xxxx')
        result = filter_matching_images([match], match.post)
        self.assertEqual(0, len(result))