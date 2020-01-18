from unittest import TestCase, mock
from unittest.mock import MagicMock

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.model.commands.repost_image_cmd import RepostImageCmd
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler


class TestSummonsHandler(TestCase):

    def test__get_summons_cmd_no_params_return_default_repost(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = 'u/repostsleuthbot'
        cmd = sum_handler._get_summons_cmd(summons, 'image')
        self.assertEqual(RepostImageCmd, type(cmd))

    def test__get_summons_cmd_no_root_command_with_params_return_default_repost(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = 'u/repostsleuthbot -all'
        cmd = sum_handler._get_summons_cmd(summons, 'image')
        self.assertEqual(RepostImageCmd, type(cmd))
        self.assertTrue(cmd.all_matches)

    def test__get_summons_repost_cmd_with_param_return_configured_cmd(self):
        config = Config(redis_host='dummy')
        sum_handler = SummonsHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)
        summons = 'u/repostsleuthbot repost -all'
        cmd = sum_handler._get_summons_cmd(summons, 'image')
        self.assertEqual(RepostImageCmd, type(cmd))
        self.assertTrue(cmd.all_matches)

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
        sub_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        sub_repo.get_by_sub.return_value = MonitoredSub(target_annoy=0.100, target_hamming=0)
        type(uow).monitored_sub = mock.PropertyMock(return_value=sub_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow

        sum_handler = SummonsHandler(uowm, MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=MagicMock())

        target_hamming, target_annoy = sum_handler._get_target_distances('test')

        self.assertEqual(0, target_hamming)
        self.assertEqual(0.1, target_annoy)

    def test__get_target_distances__no_monitored_sub(self):
        sub_repo = MagicMock()
        uow = MagicMock()
        uowm = MagicMock()
        sub_repo.get_by_sub.return_value = None
        type(uow).monitored_sub = mock.PropertyMock(return_value=sub_repo)
        uow.__enter__.return_value = uow
        uowm.start.return_value = uow
        config = Config(default_hamming_distance=3, default_annoy_distance=4.0)
        sum_handler = SummonsHandler(uowm, MagicMock(), MagicMock(), MagicMock(), MagicMock(), config=config)

        target_hamming, target_annoy = sum_handler._get_target_distances('test')

        self.assertEqual(3, target_hamming)
        self.assertEqual(4.0, target_annoy)

