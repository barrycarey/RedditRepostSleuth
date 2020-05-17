import json
import os
from unittest import TestCase

from redditrepostsleuth.core.config import Config


class TestConfig(TestCase):

    main_file = os.path.join(os.getcwd(), 'sleuth_config.json')
    alt_file = os.path.join(os.getcwd(), 'sleuth_config_alt.json')

    @classmethod
    def setUpClass(cls) -> None:
        with open(cls.main_file, 'w') as f:
            f.write(json.dumps({'log_level': 'debug'}))
        with open(cls.alt_file, 'w') as f:
            f.write(json.dumps({'log_level': 'debug'}))

    @classmethod
    def tearDownClass(cls) -> None:
        if os.path.isfile(cls.main_file):
            os.remove('sleuth_config.json')
        if os.path.isfile(cls.alt_file):
            os.remove('sleuth_config_alt.json')

    def test__load_config_file_load_order_prefer_passed_file(self):
        config_file = os.path.join(os.getcwd(), 'sleuth_config.json')
        Config.CONFIG = {}
        config = Config(config_file)
        self.assertEqual(config_file, config.CONFIG_FILE)

    def test__load_config_file_load_order_prefer_env_over_local(self):
        config_file = os.path.join(os.getcwd(), 'sleuth_config_alt.json')
        os.environ['bot_config'] = config_file
        Config.CONFIG = {}
        config = Config()
        self.assertEqual(config_file, config.CONFIG_FILE)

    def test__init_passed_override(self):
        config_file = os.path.join(os.getcwd(), 'sleuth_config_alt.json')
        os.environ['bot_config'] = config_file
        config = Config(log_level='info')
        self.assertEqual(config.log_level, 'info')

    def test__env_override(self):
        os.environ['log_level'] = 'info'
        config = Config()
        self.assertEqual(config.log_level, 'info')