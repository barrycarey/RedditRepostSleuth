from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import Mock, MagicMock, patch

from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking
from redditrepostsleuth.core.db.repository.author_activity_repo import AuthorActivityRepo


class TestAuthorActivityRepo(TestCase):
    """Tests for AuthorActivityRepo."""

    def setUp(self):
        self.mock_session = Mock()
        self.repo = AuthorActivityRepo(self.mock_session)

    def test_add_calls_session_add(self):
        activity = AuthorActivityTracking(
            post_id='abc123',
            author='testuser',
            subreddit='test',
            created_at=datetime.utcnow(),
            post_type_id=2
        )
        self.repo.add(activity)
        self.mock_session.add.assert_called_once_with(activity)

    def test_get_by_post_id_returns_result(self):
        expected = AuthorActivityTracking(post_id='abc123')
        self.mock_session.query.return_value.filter.return_value.first.return_value = expected

        result = self.repo.get_by_post_id('abc123')

        self.assertEqual(expected, result)
        self.mock_session.query.assert_called_once_with(AuthorActivityTracking)

    def test_get_by_post_id_returns_none_when_not_found(self):
        self.mock_session.query.return_value.filter.return_value.first.return_value = None

        result = self.repo.get_by_post_id('nonexistent')

        self.assertIsNone(result)

    def test_get_by_author_returns_list(self):
        expected = [
            AuthorActivityTracking(post_id='abc123', author='testuser'),
            AuthorActivityTracking(post_id='def456', author='testuser')
        ]
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = expected
        self.mock_session.query.return_value = mock_query

        result = self.repo.get_by_author('testuser', limit=10)

        self.assertEqual(expected, result)

    def test_get_by_author_without_limit(self):
        expected = [AuthorActivityTracking(post_id='abc123', author='testuser')]
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = expected
        self.mock_session.query.return_value = mock_query

        result = self.repo.get_by_author('testuser', limit=None)

        self.assertEqual(expected, result)

    def test_count_by_author_returns_count(self):
        self.mock_session.query.return_value.filter.return_value.scalar.return_value = 5

        result = self.repo.count_by_author('testuser')

        self.assertEqual(5, result)

    def test_count_by_author_returns_zero_when_none(self):
        self.mock_session.query.return_value.filter.return_value.scalar.return_value = None

        result = self.repo.count_by_author('testuser')

        self.assertEqual(0, result)

    def test_delete_older_than_returns_count(self):
        self.mock_session.query.return_value.filter.return_value.delete.return_value = 10

        cutoff = datetime.utcnow() - timedelta(days=30)
        result = self.repo.delete_older_than(cutoff)

        self.assertEqual(10, result)


class TestAuthorActivityRepoGetAuthorSubredditCounts(TestCase):
    """Tests for get_author_subreddit_counts method."""

    def setUp(self):
        self.mock_session = Mock()
        self.repo = AuthorActivityRepo(self.mock_session)

    def test_returns_subreddit_counts(self):
        expected = [('memes', 5), ('pics', 3), ('funny', 2)]
        self.mock_session.query.return_value.filter.return_value.group_by.return_value.all.return_value = expected

        result = self.repo.get_author_subreddit_counts('testuser')

        self.assertEqual(expected, result)

    def test_returns_empty_list_when_no_posts(self):
        self.mock_session.query.return_value.filter.return_value.group_by.return_value.all.return_value = []

        result = self.repo.get_author_subreddit_counts('testuser')

        self.assertEqual([], result)
