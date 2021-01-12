from datetime import datetime
from unittest import TestCase

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.notification.discord_notification_agent import DiscordAgent


class TestDiscordAgent(TestCase):

    def test_init_no_hook_or_name(self):
        self.assertRaises(ValueError, DiscordAgent)

    def test_init_no_name(self):
        self.assertRaises(ValueError, DiscordAgent, hook='test.com')

    def test_init_no_hook(self):
        self.assertRaises(ValueError, DiscordAgent, name='discord')

    def test_init(self):
        agent = DiscordAgent(name='discord', hook='test.com')
        self.assertEqual('discord', agent.name)
        self.assertEqual('test.com', agent.hook)

    def test__build_payload_no_subject(self):
        agent = DiscordAgent(name='discord', hook='test.com')
        r = agent._build_payload('this is a test message')
        self.assertIn('content', r)
        self.assertEqual('this is a test message', r['content'])

    def test__build_payload_with_subject(self):
        agent = DiscordAgent(name='discord', hook='test.com', include_subject=True)
        r = agent._build_payload('this is a test message', subject='this is a subject')
        self.assertIn('content', r)
        self.assertEqual('this is a subject\r\nthis is a test message', r['content'])

    def test__build_image_repost_attachment_single_match(self):
        agent = DiscordAgent(name='discord', hook='test.com')
        r = agent._build_image_repost_attachment(self._get_image_search_results_one_match())
        self.assertEqual(3, len(r))
        self.assertEqual('Found a repost with 1 match.', r['description'])
        self.assertIn('fields', r)
        self.assertEqual(2, len(r['fields']))

    def test__build_image_repost_attachment_multi_match(self):
        agent = DiscordAgent(name='discord', hook='test.com')
        r = agent._build_image_repost_attachment(self._get_image_search_results_multi_match())
        self.assertEqual(3, len(r))
        self.assertEqual('Found a repost with 2 matches.', r['description'])
        self.assertIn('fields', r)
        self.assertEqual(3, len(r['fields']))

    def test__build_image_repost_attachment_fields_multi_match(self):
        agent = DiscordAgent(name='discord', hook='test.com')
        r = agent._build_image_repost_attachment(self._get_image_search_results_multi_match())
        self.assertIn('fields', r)
        self.assertEqual(3, len(r['fields']))
        self.assertEqual('Offender', r['fields'][0]['name'])
        self.assertEqual('[View](https://redd.it/abc123)', r['fields'][0]['value'])
        self.assertEqual('Oldest Match', r['fields'][1]['name'])
        self.assertEqual('[View - 68.75%](https://redd.it/abc123)', r['fields'][1]['value'])
        self.assertEqual('Newest Match', r['fields'][2]['name'])
        self.assertEqual('[View - 68.75%](https://redd.it/123abc)', r['fields'][2]['value'])

    def test__build_image_repost_attachment_fields_single_match(self):
        agent = DiscordAgent(name='discord', hook='test.com')
        r = agent._build_image_repost_attachment(self._get_image_search_results_one_match())
        self.assertIn('fields', r)
        self.assertEqual(2, len(r['fields']))
        self.assertEqual('Offender', r['fields'][0]['name'])
        self.assertEqual('[View](https://redd.it/abc123)', r['fields'][0]['value'])
        self.assertEqual('Match', r['fields'][1]['name'])
        self.assertEqual('[View - 68.75%](https://redd.it/abc123)', r['fields'][1]['value'])


    def test__hex_to_int_valid(self):
        agent = DiscordAgent(name='discord', hook='test.com', color='#32b848')
        self.assertEqual(3323976, agent.hex_to_int(agent.color))

    def test__hex_to_int_invalid(self):
        agent = DiscordAgent(name='discord', hook='test.com', color='#3248')
        self.assertEqual(0, agent.hex_to_int(agent.color))


    def _get_image_search_results_one_match(self):
        search_results = ImageSearchResults('test.com', self._get_image_search_settings(),
                                            checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
        search_results.search_times = ImageSearchTimes()
        search_results.search_times.total_search_time = 10
        search_results.matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(post_id='abc123', created_at=datetime.strptime('2019-01-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        return search_results

    def _get_image_search_results_multi_match(self):
        search_results = ImageSearchResults('test.com', self._get_image_search_settings(),
                                            checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
        search_results.search_times = ImageSearchTimes()
        search_results.search_times.total_search_time = 10
        search_results.matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(post_id='abc123', created_at=datetime.strptime('2019-01-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        search_results.matches.append(
            ImageSearchMatch(
                'test.com',
                1,
                Post(post_id='123abc', created_at=datetime.strptime('2019-06-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
                10,
                10,
                32
            )
        )
        return search_results

    def _get_image_search_settings(self):
        return ImageSearchSettings(
            90,
            .077,
            target_meme_match_percent=50,
            meme_filter=False,
            max_depth=5000,
            target_title_match=90,
            max_matches=75,
            same_sub=False,
            max_days_old=190,
            filter_dead_matches=True,
            filter_removed_matches=True,
            only_older_matches=True,
            filter_same_author=True,
            filter_crossposts=True
        )