import json
from types import SimpleNamespace
from unittest import TestCase, mock
from unittest.mock import MagicMock, Mock
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.model.image_index_api_result import ImageIndexApiResult
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch


def get_mock_response(*args, **kwargs):
    class MockResponse:
        def __init__(self, text, status_code):
            self.text = text
            self.status_code = status_code

    if args[0] == 'http://good.com/image':

        return MockResponse(json.dumps(res), 200)
    if args[0] == 'http://bad.com/image':
        return MockResponse('<html></html>', 500)

class TestDuplicateImageService(TestCase):


    def test__get_matches(self):
        res = {
            'current_matches': [{'id': 1, 'distance': .234}],
            'historical_matches': [{'id': 1, 'distance': .234}],
            'index_search_time': 1.234,
            'total_searched': 100,
            'used_current_index': True,
            'used_historical_index': True,
            'target_result': {}
        }
        with mock.patch('redditrepostsleuth.core.services.duplicateimageservice.requests.get') as mock_get:
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock(index_api='http://good.com'))
            mock_get.return_value = SimpleNamespace(**{'text': json.dumps(res), 'status_code': 200})
            res = dup_svc._get_matches('111', 1, 1)
            self.assertIsInstance(res, ImageIndexApiResult)
            self.assertTrue(len(res.current_matches) == 1)
            self.assertTrue(len(res.historical_matches) == 1)

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
            mock_get.return_value = SimpleNamespace(**{'status_code': 500})
            self.assertRaises(NoIndexException, dup_svc._get_matches, '111', 1, 1)

    def test__get_matches_invalid_response_data(self):
        with mock.patch('redditrepostsleuth.core.services.duplicateimageservice.requests.get') as mock_get:
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock(index_api='http://test.com'))
            mock_get.return_value = SimpleNamespace(**{'text': json.dumps({'junk': 'data'}), 'status_code': 200})
            self.assertRaises(NoIndexException, dup_svc._get_matches, '111', 1, 1)

    def test__build_search_results(self):
        search_results = [
            {'id': 123, 'distance': .123}
        ]
        with mock.patch.object(DuplicateImageService, '_build_search_results') as dup:
            dup._set_match_posts.return_value = {}

    def test__get_post_from_index_id_valid_match_historical(self):
        def return_post_with_id(id):
            return Post(id=id)

        historical_repo = MagicMock()
        post_repo = MagicMock(get_by_post_id=MagicMock(side_effect=return_post_with_id))
        uow = MagicMock()
        uowm = MagicMock()
        historical_repo.get_by_id.return_value = MagicMock(post_id=123)
        type(uow).image_post = mock.PropertyMock(return_value=historical_repo)
        type(uow).posts = mock.PropertyMock(return_value=post_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow
        dup_svc = DuplicateImageService(uowm, Mock(), Mock(), config=MagicMock())
        r = dup_svc._get_post_from_index_id(123)
        historical_repo.get_by_id.assert_called()
        self.assertIsInstance(r, Post)
        self.assertEqual(123, r.id)

    def test__get_post_from_index_id_valid_match_current(self):
        def return_post_with_id(id):
            return Post(id=id)

        current_repo = MagicMock()
        post_repo = MagicMock(get_by_post_id=MagicMock(side_effect=return_post_with_id))
        uow = MagicMock()
        uowm = MagicMock()
        current_repo.get_by_id.return_value = MagicMock(post_id=123)
        type(uow).image_post_current = mock.PropertyMock(return_value=current_repo)
        type(uow).posts = mock.PropertyMock(return_value=post_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow
        dup_svc = DuplicateImageService(uowm, Mock(), Mock(), config=MagicMock())
        r = dup_svc._get_post_from_index_id(123, historical_index=False)
        current_repo.get_by_id.assert_called()
        self.assertIsInstance(r, Post)
        self.assertEqual(123, r.id)


    def test__get_post_from_index_id_no_index_post_found_return_none(self):

        historical_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        historical_repo.get_by_id.return_value = None
        type(uow).image_post = mock.PropertyMock(return_value=historical_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow
        dup_svc = DuplicateImageService(uowm, Mock(), Mock(), config=MagicMock())
        r = dup_svc._get_post_from_index_id(123)
        historical_repo.get_by_id.assert_called()
        self.assertIsNone(r)

    def test__get_post_from_index_id_no_post_found_return_none(self):
        historical_repo = MagicMock()
        post_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        historical_repo.get_by_id.return_value = MagicMock(id=123)
        post_repo.get_by_post_id.return_value = None
        type(uow).image_post = mock.PropertyMock(return_value=historical_repo)
        type(uow).posts = mock.PropertyMock(return_value=post_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow
        dup_svc = DuplicateImageService(uowm, Mock(), Mock(), config=MagicMock())
        r = dup_svc._get_post_from_index_id(123)
        historical_repo.get_by_id.assert_called()
        self.assertIsNone(r)

    def test__get_image_search_match_from_index_result_valid_post(self):
        with mock.patch.object(DuplicateImageService, '_get_post_from_index_id') as dup:
            dup.return_value = Post(id=456, dhash_h='40bec6703e3f3c2b0fc491a1c0c16cff273f00c00c020ff91b6807cc060c0014')
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock())
            r = dup_svc._get_image_search_match_from_index_result(
                {'id': 123, 'distance': .123},
                'test.com',
                '40bec6703e3f3c2b0fc491a1c0c16cff273f00c00c020ff91b6807cc060c0014'
            )
            self.assertIsInstance(r, ImageSearchMatch)
            self.assertEqual(123, r.index_match_id)
            self.assertEqual(456, r.post.id)

    def test__get_image_search_match_from_index_result_no_post(self):
        with mock.patch.object(DuplicateImageService, '_get_post_from_index_id') as dup:
            dup.return_value = None
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock())
            r = dup_svc._get_image_search_match_from_index_result(
                {'id': 123, 'distance': .123},
                'test.com',
                '40bec6703e3f3c2b0fc491a1c0c16cff273f00c00c020ff91b6807cc060c0014'
            )
            self.assertIsNone(r)

    def test__get_image_search_match_from_index_result_valid_post_no_dhash(self):
        with mock.patch.object(DuplicateImageService, '_get_post_from_index_id') as dup:
            dup.return_value = Post(id=456)
            dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock())
            r = dup_svc._get_image_search_match_from_index_result(
                {'id': 123, 'distance': .123},
                'test.com',
                '40bec6703e3f3c2b0fc491a1c0c16cff273f00c00c020ff91b6807cc060c0014'
            )
            self.assertIsNone(r)


    def test__remove_duplicates_one_dup_remove(self):
        matches = [
            ImageSearchMatch('test.com', 123, Post(id=1), 10, 10, 32),
            ImageSearchMatch('test.com', 123, Post(id=1), 10, 10, 32),
            ImageSearchMatch('test.com', 123, Post(id=2), 10, 10, 32)
        ]
        dup_svc = DuplicateImageService(Mock(), Mock(), Mock(), config=MagicMock())
        r = dup_svc._remove_duplicates(matches)
        self.assertEqual(2, len(r))

