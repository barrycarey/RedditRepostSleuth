from unittest import TestCase
from unittest.mock import MagicMock

from redditrepostsleuth.adminsvc.subreddit_config_update import SubredditConfigUpdater
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub


class TestSubredditConfigUpdater(TestCase):

    def test__create_wiki_config_from_database_mapped_value(self):
        config = Config(sub_monitor_exposed_config_options=['only_comment_on_repost'])
        monitored_sub = MonitoredSub(name='test', repost_only=False)
        config_updater = self.get_config_updater(config)
        r = config_updater._create_wiki_config_from_database(monitored_sub)
        self.assertTrue('only_comment_on_repost' in r)
        self.assertFalse(r['only_comment_on_repost'])

    def test__create_wiki_config_from_database_unmapped_value(self):
        config = Config(sub_monitor_exposed_config_options=['remove_repost'])
        monitored_sub = MonitoredSub(name='test', remove_repost=True)
        config_updater = self.get_config_updater(config)
        r = config_updater._create_wiki_config_from_database(monitored_sub)
        self.assertTrue('remove_repost' in r)
        self.assertTrue(r['remove_repost'])

    def test__update_monitored_sub_from_wiki_unmapped_value(self):
        config = Config(sub_monitor_exposed_config_options=['remove_repost'])
        monitored_sub = MonitoredSub(name='test', remove_repost=False)
        config_updater = self.get_config_updater(config)
        config_updater._update_monitored_sub_from_wiki(monitored_sub, {'remove_repost': True})
        self.assertTrue(monitored_sub.remove_repost)

    def test__get_missing_config_values_one_missing(self):
        config = Config(sub_monitor_exposed_config_options=['only_comment_on_repost', 'repost_only'])
        monitored_sub = MonitoredSub(name='test', repost_only=False)
        config_updater = self.get_config_updater(config)
        r = config_updater._get_missing_config_values( {'repost_only': True})
        self.assertTrue(len(r) == 1)
        self.assertTrue('only_comment_on_repost' in r)

    def test__update_monitored_sub_from_wiki_handle_list(self):
        config = Config(sub_monitor_exposed_config_options=['title_ignore_keywords'])
        config_updater = self.get_config_updater(config)
        wiki_config = {'title_ignore_keywords': ['test1']}
        monitored_sub = MonitoredSub(name='test')
        config_updater._update_monitored_sub_from_wiki(monitored_sub, wiki_config)
        self.assertTrue(type(monitored_sub.title_ignore_keywords) == str)
        self.assertEqual('["test1"]', monitored_sub.title_ignore_keywords)

    def test__create_wiki_config_from_database(self):
        config = Config(sub_monitor_exposed_config_options=['title_ignore_keywords'])
        config_updater = self.get_config_updater(config)
        wiki_config = {'title_ignore_keywords': ['test1']}
        monitored_sub = MonitoredSub(title_ignore_keywords='["test"]')

    def get_config_updater(self, config: Config):
        uowm = MagicMock()
        reddit = MagicMock()
        res_handler = MagicMock()
        return SubredditConfigUpdater(uowm, reddit, res_handler, config)