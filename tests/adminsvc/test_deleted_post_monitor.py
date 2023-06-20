from unittest import TestCase, IsolatedAsyncioTestCase

import pytest

from redditrepostsleuth.adminsvc.deleted_post_monitor import build_reddit_req_url, get_post_ids_from_reddit_req_url, \
    db_ids_from_post_ids, merge_results
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.misc_models import DeleteCheckResult, BatchedPostRequestJob, JobStatus


@pytest.mark.asyncio
class TestDeletedPostMonitorAsync(IsolatedAsyncioTestCase):
    pass

class TestDeletedPostMonitor(TestCase):
    def test_build_reddit_req_url(self):
        post_ids = ['1216baz', '1216baw', '1216bao']
        expected = 'https://api.reddit.com/api/info?id=t3_1216baz,t3_1216baw,t3_1216bao'
        self.assertEqual(expected, build_reddit_req_url(post_ids))

    def test_get_post_ids_from_reddit_req_url(self):
        expected = ['1216baz', '1216baw', '1216bao']
        url = 'https://api.reddit.com/api/info?id=t3_1216baz,t3_1216baw,t3_1216bao'
        result = get_post_ids_from_reddit_req_url(url)
        self.assertEqual(expected, result)

    def test_db_ids_from_post_ids_all_valid_return_all(self):
        post_ids = ['abc123', 'abc345', 'abc456']
        expected = [12345,22345,32345]
        posts = [
            Post(id=12345, post_id='abc123'),
            Post(id=22345, post_id='abc345'),
            Post(id=32345, post_id='abc456'),
        ]
        result = db_ids_from_post_ids(post_ids, posts)

        self.assertEqual(expected, result)

    def test_db_ids_from_post_ids_missing_one_return_two(self):
        post_ids = ['abc123', 'abc345',]
        expected = [12345,22345]
        posts = [
            Post(id=12345, post_id='abc123'),
            Post(id=22345, post_id='abc345'),
            Post(id=32345, post_id='abc456'),
        ]
        result = db_ids_from_post_ids(post_ids, posts)

        self.assertEqual(expected, result)

    def test_merge_results(self):
        results_one = DeleteCheckResult(
            to_delete=['sdfsdf', 'asdfsdf'], to_update=['sahdf', 'kjelikj'], to_recheck=['sadfd']
        )
        results_two = DeleteCheckResult(
            to_delete=['klkl;',], to_update=['safhdf', 'kjsdikj', 'eflodf'], to_recheck=['weree']
        )

        merged = merge_results([results_one, results_two])
        self.assertEqual(5, len(merged.to_update))
        self.assertEqual(3, len(merged.to_delete))
        self.assertEqual(2, len(merged.to_recheck))
        self.assertEqual(10, merged.count)
