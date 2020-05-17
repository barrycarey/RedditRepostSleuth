from unittest import TestCase
from unittest.mock import MagicMock

from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.model.imagematch import ImageMatch


class TestDuplicateImageService(TestCase):

    def test__zip_annoy_results(self):
        dup = DuplicateImageService(MagicMock(), MagicMock(), config=MagicMock())
        annoy_results = (
            [1,2,3],
            ['a','b','c']
        )
        r = dup._zip_annoy_results(annoy_results)
        self.assertIn((1,'a'), r)

    def test__convert_annoy_results(self):
        dup = DuplicateImageService(MagicMock(), MagicMock(), config=MagicMock())
        annoy_results = [
            {'id': 1, 'distance': 0.200},
            {'id': 2, 'distance': 0.500}
        ]
        r = dup._convert_annoy_results(annoy_results, 1234)

        self.assertEqual(r[0].annoy_distance, 0.2)
        self.assertEqual(r[0].original_id, 1234)


    def test__annoy_filter(self):
        dup = DuplicateImageService(MagicMock(), MagicMock(), config=MagicMock())
        target_distance = 0.265
        test_input = [
            {'id': 1, 'distance': 0.300},
            {'id': 2, 'distance': 0.200},
            {'id': 3, 'distance': 0.350},
            {'id': 4, 'distance': 0.264}
        ]
        a_filter = dup._annoy_filter(target_distance)
        r = list(filter(a_filter, test_input))
        self.assertEqual(2, len(r))
        self.assertEqual(2, r[0]['id'])
        self.assertEqual(4, r[1]['id'])

    def test__merge_search_results(self):
        dup = DuplicateImageService(MagicMock(), MagicMock(), config=MagicMock())
        match1 = ImageMatch()
        match1.match_id = 1
        match2 = ImageMatch()
        match2.match_id = 2
        match3 = ImageMatch()
        match3.match_id = 3
        match4 = ImageMatch()
        match4.match_id = 4
        match5 = ImageMatch()
        match5.match_id = 5

        r1 = [match1,match2,match3]
        r2 = [match3,match4,match5]
        result = dup._merge_search_results(r1, r2)
        self.assertEqual(len(result), 5)

