from unittest import TestCase

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.util.repost_filters import cross_post_filter, same_sub_filter, annoy_distance_filter, \
    hamming_distance_filter


class TestCross_post_filter(TestCase):
    def test_cross_post_filter__remove_crosspost(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match1.post = Post()
        match2.post = Post(crosspost_parent='sdfsdf')
        matches.append(match1)
        matches.append(match2)
        r = list(filter(cross_post_filter, matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].match_id)

    def test_same_sub_filter__remove_same_sub(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match1.post = Post(subreddit='sub1')
        match2.post = Post(subreddit='sub2')
        matches.append(match1)
        matches.append(match2)
        r = list(filter(same_sub_filter('sub2'), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(2, r[0].match_id)

    def annoy_distance_filter__remove_higher_distance(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match3 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.hamming_distance = 10
        match2.annoy_distance = 20
        match3.annoy_distance = 25
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(hamming_distance_filter(11), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].match_id)