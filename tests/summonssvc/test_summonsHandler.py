from unittest import TestCase, mock
from unittest.mock import MagicMock

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler


class TestSummonsHandler(TestCase):
    def test_handle_summons(self):
        self.fail()

    def test_handle_repost_request(self):
        self.fail()

    def test_process_repost_request(self):
        self.fail()

    def test_process_link_repost_request(self):
        self.fail()

    def test_process_image_repost_request(self):
        self.fail()

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

    def test__send_response(self):
        self.fail()

    def test__save_response(self):
        self.fail()

    def test__save_post(self):
        self.fail()

    def test_save_unknown_post(self):
        self.fail()

    def test__searched_post_str(self):
        self.fail()

    def test__send_event(self):
        self.fail()
