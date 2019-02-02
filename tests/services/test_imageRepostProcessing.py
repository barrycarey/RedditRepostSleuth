from unittest import TestCase, mock

from praw.models import Submission

from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.model.db.databasemodels import Post
from datetime import datetime

from redditrepostsleuth.service.imagerepost import ImageRepostProcessing


class TestImageRepostProcessing(TestCase):
    def test_generate_hashes(self):
        self.fail()

    @mock.patch('redditrepostsleuth.db.uow.unitofworkmanager.UnitOfWorkManager')
    @mock.patch('redditrepostsleuth.service.imagerepost.generate_img_by_url')
    @mock.patch('praw.models.Submission')
    def test_find_all_occurrences_failed_image_conversion(self, uowm, gen_image, submission):
        gen_image.return_value = ImageConversioinException('error')
        repost_service = ImageRepostProcessing(uowm)
        result = repost_service.find_all_occurrences(submission)
        self.assertEqual(result.status, 'error')

    def test_clear_deleted_images(self):
        self.fail()

    def test__handle_reposts(self):
        self.fail()

    @mock.patch('redditrepostsleuth.db.uow.unitofworkmanager.UnitOfWorkManager')
    def test__clean_reposts(self, uowm):
        posts = get_list_of_posts()
        posts[0].crosspost_parent = '1111'
        removed_post = posts[0]
        repost_service = ImageRepostProcessing(uowm)
        result = repost_service._clean_reposts(posts)
        self.assertFalse(removed_post in result)


    @mock.patch('redditrepostsleuth.db.uow.unitofworkmanager.UnitOfWorkManager')
    def test__sort_reposts(self, uowm, reddit):
        oldest_date = datetime.strptime('2019-01-30 23:49:44', '%Y-%m-%d %H:%M:%S')
        posts = get_list_of_posts()
        repost = ImageRepostProcessing(uowm)
        result = repost._sort_reposts(posts)
        self.assertEqual(result[0].created_at, oldest_date)


def get_list_of_posts():
    posts = []
    posts.append(
        Post(
            post_id='1',
            created_at=datetime.strptime('2019-01-31 01:53:19', '%Y-%m-%d %H:%M:%S')
        )
    )

    posts.append(
        Post(
            post_id='2',
            created_at=datetime.strptime('2019-01-30 23:49:44', '%Y-%m-%d %H:%M:%S')
        )
    )
    posts.append(
        Post(
            post_id='3',
            created_at=datetime.strptime('2019-02-02 03:16:49', '%Y-%m-%d %H:%M:%S')
        )
    )

    return posts