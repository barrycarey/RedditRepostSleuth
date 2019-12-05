from unittest import TestCase

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from datetime import datetime

from redditrepostsleuth.core.util.reposthelpers import sort_reposts


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