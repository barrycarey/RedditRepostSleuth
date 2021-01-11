from unittest import TestCase, mock
from unittest.mock import MagicMock

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.model.commands.repost_image_cmd import RepostImageCmd
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler


class TestSummonsHandler(TestCase):

    def test__strip_summons_flags__clean_input_usertag(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = '/repostsleuthbot'
        self.assertIsNone(sum_handler._strip_summons_flags(summons))

    def test__strip_summons_flags__junk_input_usertag(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = 'This test u/repostsleuthbot some junk'
        self.assertEqual(sum_handler._strip_summons_flags(summons), 'some junk')

    def test__strip_summons_flags__clean_input_commandtag(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = '?repost'
        self.assertEqual(sum_handler._strip_summons_flags(summons), '')

    def test__strip_summons_flags__junk_input_commandtag(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = 'This test ?repost some junk'
        self.assertEqual(sum_handler._strip_summons_flags(summons), 'some junk')

    def test__strip_summons_flags__junk_input_commandtag(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = 'This test ?repost some junk'
        self.assertEqual(sum_handler._strip_summons_flags(summons), 'some junk')

    def test__get_target_distances__monitored_sub(self):
        monitored_sub = MonitoredSub(target_image_match=98, target_image_meme_match=5)
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=MagicMock(default_annoy_distance=0.777))
        target_image_match, target_image_meme_match, target_annoy = sum_handler._get_target_distances(monitored_sub)
        self.assertEqual(98, target_image_match)
        self.assertEqual(5, target_image_meme_match)

