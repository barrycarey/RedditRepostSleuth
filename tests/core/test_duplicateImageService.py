from unittest import TestCase
from unittest.mock import MagicMock

from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.model.imagematch import ImageMatch


class TestDuplicateImageService(TestCase):
    def test__load_index_files(self):
        self.fail()

    def test__load_current_index_file(self):
        self.fail()

    def test__load_historical_index_file(self):
        self.fail()

    def test__filter_results_for_reposts(self):
        self.fail()

    def test_check_duplicates_wrapped(self):
        self.fail()

    def test__search_index_by_vector(self):
        self.fail()

    def test__search_index_by_id(self):
        self.fail()

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
            (1, 0.200),
            (2, 0.500)
        ]
        r = dup._convert_annoy_results(annoy_results, 1234)

        self.assertEqual(r[0].annoy_distance, 0.2)
        self.assertEqual(r[0].original_id, 1234)


    def test__annoy_filter(self):
        dup = DuplicateImageService(MagicMock(), MagicMock(), config=MagicMock())
        target_distance = 0.265
        test_input = [
            (1, 0.300),
            (2, 0.200),
            (3, 0.350),
            (4, 0.264)
        ]
        a_filter = dup._annoy_filter(target_distance)
        r = list(filter(a_filter, test_input))
        self.assertEqual(2, len(r))
        self.assertEqual(2, r[0][0])
        self.assertEqual(4, r[1][0])

    def test__log_search_time(self):
        self.fail()

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

    def test__set_match_posts_historical(self):
        self.fail()

    def test_get_meme_template(self):
        self.fail()

    def test__set_match_hamming(self):
        self.fail()

    def test__final_meme_filter(self):
        self.fail()
