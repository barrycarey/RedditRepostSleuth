import configparser
import json
import os
import sys
from typing import List



class _NotSet:
    def __bool__(self):
        return False

    __nonzero__ = __bool__

    def __str__(self):
        return 'NotSet'

class Config:
    """ Class containing all the config data.
    This is based on Praw's own config class because I'm an unoriginal bastard"""

    CONFIG = None
    CONFIG_NOT_SET = _NotSet()

    @classmethod
    def _load_config(cls, config_file=None):

        if config_file:
            print(f'Checking provided config file: {config_file}')
            if not os.path.isfile(config_file):
                print('Provided config file is invalid')
                config_file = None

        module_dir = os.path.dirname(sys.modules[__name__].__file__)
        print('Checking for config in module dir:' + module_dir)
        if os.path.isfile(os.path.join(module_dir, 'sleuth_config.json')):
            config_file = os.path.join(module_dir, 'sleuth_config.json')

        print(f'Checking for config in current dir: {os.getcwd()}')
        if os.path.isfile('sleuth_config.json'):
            config_file = os.path.join(os.getcwd(), 'sleuth_config.json')

        print('Checking ENV for config file')
        if os.getenv('bot_config', None):
            if os.path.isfile(os.getenv('bot_config')):
                config_file = os.getenv('bot_config')

        if config_file is None:
            print('Unable to locate sleuth_config.json')
            sys.exit(1)

        print(f'Loading Config {config_file}')
        with open(config_file, 'r') as f:
            cls.CONFIG = json.loads(f.read())

    @staticmethod
    def _flatten_config(cfg: dict):
        r = {}
        for k, v in cfg.items():
            if isinstance(v, dict):
                r = {**r, **Config._flatten_config(v)}
                continue
            r[k] = v
        return r

    def __init__(self, config_file=None, **settings):

        if Config.CONFIG is None:
            self._load_config(config_file)

        self.custom = Config._flatten_config(Config.CONFIG)

        self._settings = self.custom = settings
        self.custom = Config._flatten_config(Config.CONFIG)

        self._initialize_attributes()

    def _fetch_or_not_set(self, key):
        if key in self._settings:
            return self._fetch(key)

        env_value = os.getenv(key)
        ini_value = self._fetch_deafult(key)

        return env_value or ini_value or self.CONFIG_NOT_SET

    def _fetch(self, key):
        value = self.custom[key]
        del self.custom[key]
        return value

    def _fetch_deafult(self, key, default=None):
        if key not in self.custom:
            return default
        return self._fetch(key)


    def _initialize_attributes(self):
        attrbs = [
            'redis_host',
            'redis_password',
            'redis_port',
            'db_host',
            'db_port',
            'db_user',
            'db_password',
            'db_name',
            'reddit_client_id',
            'reddit_client_secret',
            'reddit_useragent',
            'reddit_username',
            'reddit_password',
            'influx_host',
            'influx_port',
            'influx_user',
            'influx_password',
            'influx_database',
            'influx_verify_ssl',
            'log_level',
            'index_current_max_age',
            'index_current_skip_load_age',
            'index_current_file',
            'index_historical_skip_load_age',
            'index_historical_file',
            'default_hamming_distance',
            'default_annoy_distance',
            'repost_image_check_on_ingest',
            'repost_link_check_on_ingest',
            'image_hash_api'
        ]

        for attribute in attrbs:
            setattr(self, attribute, self._fetch_or_not_set(attribute))


