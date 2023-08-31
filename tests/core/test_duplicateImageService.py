import json
from types import SimpleNamespace
from unittest import TestCase, mock
from unittest.mock import MagicMock, Mock
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch



class TestDuplicateImageService(TestCase):


    def test__get_matches_connection_error(self):
        with mock.patch('redditrepostsleuth.core.services.duplicateimageservice.requests.get') as mock_get:
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock(index_api='http://test.com'))
            mock_get.side_effect = ConnectionError('ouch!')
            self.assertRaises(NoIndexException, dup_svc._get_matches, '111', 1, 1)

    def test__get_matches_unknown_exception(self):
        with mock.patch('redditrepostsleuth.core.services.duplicateimageservice.requests.get') as mock_get:
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock(index_api='http://test.com'))
            mock_get.side_effect = Exception('Ouch')
            self.assertRaises(Exception, dup_svc._get_matches, '111', 1, 1)

    def test__get_matches_bad_status_code(self):
        with mock.patch('redditrepostsleuth.core.services.duplicateimageservice.requests.get') as mock_get:
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock(index_api='http://test.com'))
            mock_get.return_value = SimpleNamespace(**{'status_code': 500, 'text': 'result'})
            self.assertRaises(NoIndexException, dup_svc._get_matches, '111', 1, 1)


    def test__build_search_results(self):
        search_results = [
            {'id': 123, 'distance': .123}
        ]
        with mock.patch.object(DuplicateImageService, '_build_search_results') as dup:
            dup._set_match_posts.return_value = {}

    def test__remove_duplicates_one_dup_remove(self):
        matches = [
            ImageSearchMatch('test.com', 123, Post(id=1), 10, 10, 32),
            ImageSearchMatch('test.com', 123, Post(id=1), 10, 10, 32),
            ImageSearchMatch('test.com', 123, Post(id=2), 10, 10, 32)
        ]
        dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock())
        r = dup_svc._remove_duplicates(matches)
        self.assertEqual(2, len(r))

