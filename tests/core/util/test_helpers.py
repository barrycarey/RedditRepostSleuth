import os
from unittest import TestCase
from datetime import datetime
from unittest.mock import patch

from PIL import Image

from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate
from redditrepostsleuth.core.exception import ImageConversioinException
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper

from redditrepostsleuth.core.util.helpers import chunk_list, searched_post_str, create_first_seen, create_meme_template, \
    post_type_from_url, build_markdown_list, build_msg_values_from_search, build_image_msg_values_from_search


class TestHelpers(TestCase):

    def test_chunklist(self):
        l = list(range(15))
        chunks = list(chunk_list(l, 5))
        self.assertEqual(len(chunks), 3)

    def test_searched_post_str_valid_count(self):
        post = Post(post_type='image')
        r = searched_post_str(post, 10)
        expected = '**Searched Images:** 10'
        self.assertEqual(expected, r)

    def test_searched_post_str_link_valid_count(self):
        post = Post(post_type='link')
        r = searched_post_str(post, 10)
        expected = '**Searched Links:** 10'
        self.assertEqual(expected, r)

    def test_searched_post_str_unknowntype_valid_count(self):
        post = Post(post_type='video')
        r = searched_post_str(post, 10)
        expected = '**Searched:** 10'
        self.assertEqual(expected, r)

    def test_searched_post_str_formatting(self):
        post = Post(post_type='image')
        r = searched_post_str(post, 1000000)
        expected = '**Searched Images:** 1,000,000'
        self.assertEqual(expected, r)

    def test_first_seen_valid_input(self):
        post = Post(subreddit='somesub', post_id='1234', created_at=datetime.fromtimestamp(1572799193))
        r = create_first_seen(post, 'somesub')
        expected = f'First seen [Here](https://redd.it/1234) on {post.created_at.strftime("%Y-%m-%d")}'
        self.assertEqual(expected, r)

    def test_first_seen_no_link_sub_valid_input(self):
        post = Post(subreddit='somesub', post_id='1234', created_at=datetime.fromtimestamp(1572799193))
        r = create_first_seen(post, 'natureismetal')
        expected = f'First seen in somesub on {post.created_at.strftime("%Y-%m-%d")}'
        self.assertEqual(expected, r)

    """
    @patch('redditrepostsleuth.core.util.helpers.generate_img_by_url')
    def test_create_meme_template_valid_url(self, generate_img_by_url):
        url = 'https://i.imgur.com/oIxwC9M.jpg'
        img = Image.open(os.path.join(os.getcwd(), 'data', 'demo.jpg'))
        generate_img_by_url.return_value = img
        template = create_meme_template(url)

        self.assertEqual('3ffeffffffffffffffffffffffff7ffe3ffc0180018003800000000000000000', template.ahash)
        self.assertEqual('ff00ff00ff00ff00ff00ff00ff00ff00fe00ff00f700fe00f260308102200000', template.dhash_h)
        self.assertEqual('fffffffffffffffffffe0fe00180000000000000ffc10b7ff0000400033c0000', template.dhash_v)
        self.assertEqual(url, template.example)
        self.assertEqual(10, template.template_detection_hamming)
    """
    @patch('redditrepostsleuth.core.util.helpers.generate_img_by_url')
    def test_create_meme_template_raise_exception(self, generate_img_by_url):
        url = 'https://i.imgur.com/oIxwC9M.jpg'
        generate_img_by_url.side_effect = ImageConversioinException('broke')
        self.assertRaises(ImageConversioinException, create_meme_template, url)

    def test_post_type_from_url_image_lowercase(self):
        self.assertEqual('image', post_type_from_url('www.example.com/test.jpg'))

    def test_post_type_from_url_image_uppercase(self):
        self.assertEqual('image', post_type_from_url('www.example.com/test.Jpg'))

    def test_build_markdown_list_valid(self):
        match = ImageMatch()
        match.post = Post(created_at=datetime.fromtimestamp(1572799193),
                                shortlink='http://redd.it',
                                subreddit='somesub',
                                post_id='1234')
        match.hamming_distance = 5
        expected = f'* {match.post.created_at.strftime("%d-%m-%Y")} - [https://redd.it/1234](https://redd.it/1234) [{match.post.subreddit}] [95.00% match]\n'
        self.assertEqual(expected, build_markdown_list([match]))

    def build_image_msg_values_from_search_include_meme_template(self):
        match1 = ImageMatch()
        match1.hamming_distance = 5
        match1.post = Post(url='www.example.com',
                           created_at=datetime.fromtimestamp(1572799193),
                           post_id='1234',
                           subreddit='somesub')
        wrapper = ImageRepostWrapper()
        wrapper.matches.append(match1)
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(subreddit='sub2')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        wrapper.meme_template = MemeTemplate(id=10)
        result = build_image_msg_values_from_search(wrapper)
        self.assertIn('meme_template_id', result)
        self.assertEqual(10, result['meme_template_id'])

    def build_image_msg_values_from_search_include_false_positive_data(self):
        match1 = ImageMatch()
        match1.hamming_distance = 5
        match1.post = Post(url='www.example.com',
                           created_at=datetime.fromtimestamp(1572799193),
                           post_id='1234',
                           subreddit='somesub')
        wrapper = ImageRepostWrapper()
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(post_id=1234)
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        wrapper.meme_template = MemeTemplate(id=10)
        result = build_image_msg_values_from_search(wrapper)
        self.assertIn('false_positive_data', result)
        self.assertEqual(result['false_positive_data'], '{"post": "https://redd.it/1234", "meme_template": 10}')

    def build_image_msg_values_from_search_correct_match_percent(self):
        match1 = ImageMatch()
        match1.hamming_distance = 5
        match1.hamming_match_percent = 96.78
        match1.post = Post(url='www.example.com',
                           created_at=datetime.fromtimestamp(1572799193),
                           post_id='1234',
                           subreddit='somesub')
        wrapper = ImageRepostWrapper()
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(post_id=1234)
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        wrapper.meme_template = MemeTemplate(id=10)
        result = build_image_msg_values_from_search(wrapper)
        self.assertEqual('96.78%', result['newest_percent_match'])

    def test_build_msg_values_from_search_key_total(self):
        match1 = ImageMatch()
        match1.hamming_distance = 5
        match1.post = Post(url='www.example.com',
                           created_at=datetime.fromtimestamp(1572799193),
                           post_id='1234',
                           subreddit='somesub')
        wrapper = ImageRepostWrapper()
        wrapper.matches.append(match1)
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(subreddit='sub2')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111

        result = build_msg_values_from_search(wrapper)

        self.assertEqual(18, len(result.keys()))
        # TODO - Maybe test return values.  Probably not needed

    def test_build_msg_values_from_search_no_match_key_total(self):
        wrapper = ImageRepostWrapper()
        wrapper.checked_post = Post(subreddit='sub2')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        result = build_msg_values_from_search(wrapper)

        self.assertEqual(8, len(result.keys()))

    def test_build_msg_values_from_search_no_match_custom_key_total(self):
        wrapper = ImageRepostWrapper()
        wrapper.checked_post = Post(subreddit='sub2')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111
        result = build_msg_values_from_search(wrapper, test1='test')

        self.assertEqual(9, len(result.keys()))

    def test_build_msg_values_from_search_extra_values(self):
        match1 = ImageMatch()
        match1.hamming_distance = 5
        match1.post = Post(url='www.example.com',
                           created_at=datetime.fromtimestamp(1572799193),
                           post_id='1234',
                           subreddit='somesub')
        wrapper = ImageRepostWrapper()
        wrapper.matches.append(match1)
        wrapper.matches.append(match1)
        wrapper.checked_post = Post(subreddit='sub2')
        wrapper.total_searched = 100
        wrapper.total_search_time = 0.111

        result = build_msg_values_from_search(wrapper, item1='value1', item2='value2')

        self.assertTrue('item1' in result)
        self.assertTrue('item2' in result)
        self.assertEqual(result['item1'], 'value1')
        self.assertEqual(result['item2'], 'value2')