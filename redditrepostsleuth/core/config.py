import configparser
import os
from typing import List

from redditrepostsleuth.core.config_base import ConfigBase

class _NotSet:
    def __bool__(self):
        return False

    __nonzero__ = __bool__

    def __str__(self):
        return 'NotSet'

class Config(ConfigBase):
    """ Class containing all the config data.
    This is based on Praw's own config class because I'm an unoriginal bastard"""

    CONFIG = None
    CONFIG_NOT_SET = _NotSet()

    @classmethod
    def _load_config(cls):
        config = configparser.RawConfigParser()
        # TODO - Add logic to search for config locations
        config_file = os.path.join(os.getcwd(), 'config_dev.ini')
        config.read(config_file)
        cls.CONFIG = config

    def __init__(self, service_names: List[str], **settings):

        if Config.CONFIG is None:
            self._load_config()

        self._settings = self.custom = settings
        for svc in service_names:
            self.custom = dict(Config.CONFIG.items(svc), **self.custom)

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
            'log_level'
        ]

        for attribute in attrbs:
            setattr(self, attribute, self._fetch_or_not_set(attribute))


