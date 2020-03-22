from datetime import datetime
from unittest import TestCase
from unittest.mock import patch

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.util.repost_filters import cross_post_filter, same_sub_filter, annoy_distance_filter, \
    hamming_distance_filter, filter_newer_matches, filter_days_old_matches, filter_same_author, filter_same_post, \
    filter_title_keywords


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

    def test_hamming_distance_filter__remove_higher_distance(self):
        matches = []
        match1 = ImageMatch()
        match1.post = Post(id=1)
        match2 = ImageMatch()
        match2.post = Post(id=2)
        match3 = ImageMatch()
        match3.post = Post(id=3)
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.hamming_distance = 10
        match2.hamming_distance = 20
        match3.hamming_distance = 25
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(hamming_distance_filter(11), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].match_id)

    def test_annoy_distance_filter__remove_higher_distance(self):
        matches = []
        match1 = ImageMatch()
        match1.post = Post(id=1)
        match2 = ImageMatch()
        match2.post = Post(id=2)
        match3 = ImageMatch()
        match3.post = Post(id=3)
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.annoy_distance = 0.100
        match2.annoy_distance = 0.200
        match3.annoy_distance = 0.250
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(annoy_distance_filter(0.150), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].match_id)

    def test_filter_newer_matches__remove_newer(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match3 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.post = Post(created_at=datetime.utcfromtimestamp(1574168050))
        match2.post = Post(created_at=datetime.utcfromtimestamp(1574081650))
        match3.post = Post(created_at=datetime.utcfromtimestamp(1573908850))
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(filter_newer_matches(datetime.utcfromtimestamp(1573995250)), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].match_id)

    def test_filter_days_old_matches__remove_older(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match3 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.post = Post(created_at=datetime.utcfromtimestamp(1571349660))
        match2.post = Post(created_at=datetime.utcfromtimestamp(1571090460))
        match3.post = Post(created_at=datetime.utcfromtimestamp(1570917660))
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        with patch('redditrepostsleuth.core.util.repost_filters.datetime') as mock_date:
            mock_date.utcnow.return_value = datetime.utcfromtimestamp(1571360460)
            r = list(filter(filter_days_old_matches(2), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(1, r[0].match_id)

    def test_filter_newer_matches__remove_newer(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match3 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.post = Post(author='barry')
        match2.post = Post(author='barry')
        match3.post = Post(author='steve')
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(filter_same_author('barry'), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].match_id)

    def test_filter_same_post__remove_same(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match3 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.post = Post(post_id='1111')
        match2.post = Post(post_id='2222')
        match3.post = Post(post_id='3333')
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(filter_same_post('3333'), matches))
        self.assertEqual(len(r), 2)
        self.assertEqual(1, r[0].match_id)
        self.assertEqual(2, r[1].match_id)

    def test_filter_title_keywords(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match3 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.post = Post(post_id='1111', title='Some repost title')
        match2.post = Post(post_id='2222', title='This is a repost')
        match3.post = Post(post_id='3333', title='some normal title')
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(filter_title_keywords(['repost']), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].match_id)

    def test_filter_title_keywords_uppercase__remove_keyword(self):
        matches = []
        match1 = ImageMatch()
        match2 = ImageMatch()
        match3 = ImageMatch()
        match1.match_id = 1
        match2.match_id = 2
        match3.match_id = 3
        match1.post = Post(post_id='1111', title='SOME REPOSTTITLE')
        match2.post = Post(post_id='2222', title='THIS IS A REPOST')
        match3.post = Post(post_id='3333', title='NORMAL TITLE')
        matches.append(match1)
        matches.append(match2)
        matches.append(match3)
        r = list(filter(filter_title_keywords(['repost']), matches))
        self.assertEqual(len(r), 1)
        self.assertEqual(3, r[0].match_id)