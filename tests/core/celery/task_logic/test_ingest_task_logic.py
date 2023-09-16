from unittest import TestCase

from redditrepostsleuth.core.celery.task_logic.ingest_task_logic import image_links_from_gallery_meta_data
from redditrepostsleuth.core.exception import GalleryNotProcessed


class TestIngestTasks(TestCase):

    def test_image_links_from_gallery_meta_data_return_jpg_links(self):
        meta_data = {
            'abcd123': {
                'status': 'valid',
                'm': 'image/jpg'
            }
        }
        expected = ['https://i.redd.it/abcd123.jpg']
        self.assertListEqual(expected, image_links_from_gallery_meta_data(meta_data))

    def test_image_links_from_gallery_meta_data_return_png_links(self):
        meta_data = {
            'abcd456': {
                'status': 'valid',
                'm': 'image/png'
            }
        }
        expected = ['https://i.redd.it/abcd456.png']
        self.assertListEqual(expected, image_links_from_gallery_meta_data(meta_data))

    def test_image_links_from_gallery_meta_data_return_gif_links(self):
        meta_data = {
            'abcd456': {
                'status': 'valid',
                'm': 'image/gif'
            }
        }
        expected = ['https://i.redd.it/abcd456.gif']
        self.assertListEqual(expected, image_links_from_gallery_meta_data(meta_data))

    def test_image_links_from_gallery_meta_data_return_mixed_links(self):
        meta_data = {
            'abcd123': {
                'status': 'valid',
                'm': 'image/jpg'
            },
            'abcd456': {
                'status': 'valid',
                'm': 'image/png'
            }
        }
        expected = ['https://i.redd.it/abcd123.jpg', 'https://i.redd.it/abcd456.png']
        self.assertListEqual(expected, image_links_from_gallery_meta_data(meta_data))

    def test_image_links_from_gallery_meta_data_no_valid_type_raises_key_error(self):
        meta_data = {
            'abcd123': {
                'status': 'valid',
                'm': 'image/test'
            },
        }
        with self.assertRaises(KeyError):
            image_links_from_gallery_meta_data(meta_data)

    def test_image_links_from_gallery_meta_data_image_still_processing_raises(self):
        meta_data = {
            'abcd123': {
                'status': 'processing',
                'm': 'image/test'
            },
        }
        with self.assertRaises(GalleryNotProcessed):
            image_links_from_gallery_meta_data(meta_data)

    def test_image_links_from_gallery_meta_data_unknown_status_processing_throws(self):
        meta_data = {
            'abcd123': {
                'status': 'unknown',
                'm': 'image/test'
            },
        }
        with self.assertRaises(ValueError):
            image_links_from_gallery_meta_data(meta_data)