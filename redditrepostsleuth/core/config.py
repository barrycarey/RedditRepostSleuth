import configparser
import json
import os
import sys
from typing import List, Tuple, Text, NoReturn

from redditrepostsleuth.core.logging import log


class _NotSet:
    def __bool__(self):
        return False

    __nonzero__ = __bool__

    def __str__(self):
        return 'NotSet'

class Config:
    """ Class containing all the config data.
    This is based on Praw's own config class because I'm an unoriginal bastard"""

    CONFIG = {}
    CONFIG_FILE = None
    CONFIG_NOT_SET = _NotSet()

    @classmethod
    def _load_config(cls, config_file=None) -> NoReturn:
        """
        Load the config file.

        Config file can either be passed in, pulled from the ENV, in CWD or in module dir.

        Load priority:
        1. Passed in config
        2. ENV
        3. CWD
        4 Module Dir
        :param config_file: path to config file
        :return: None
        """
        config_to_load = ()

        module_dir = os.path.dirname(sys.modules[__name__].__file__)
        log.info('Checking for config in module dir: %s', module_dir)
        if os.path.isfile(os.path.join(module_dir, 'sleuth_config.json')):
            log.info('Found sleuth_config.json in module dir')
            config_to_load = os.path.join(module_dir, 'sleuth_config.json'), 'module'

        log.info(f'Checking for config in current dir: %s', os.getcwd())
        if not config_to_load and os.path.isfile('sleuth_config.json'):
            log.info('Found sleuth_config.json in current directory')
            config_to_load = os.path.join(os.getcwd(), 'sleuth_config.json'), 'cwd'

        log.info('Checking ENV for config file')
        if os.getenv('bot_config', None):
            if os.path.isfile(os.getenv('bot_config')):
                config_to_load = os.getenv('bot_config'), 'env'
                log.info('Loading config provided in ENV: %s', config_to_load)

        if config_file:
            log.info('Checking provided config file: %s', config_file)
            if os.path.isfile(config_file):
                config_to_load = config_file, 'passed'
            else:
                log.error('Provided config does not exist')

        if not config_to_load:
            log.error('Failed to locate config file')
            return

        log.info('Config Source: %s | Config File: %s', config_to_load[1], config_to_load[0])
        cls.CONFIG_FILE = config_to_load[0]
        with open(config_to_load[0], 'r') as f:
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

        if not Config.CONFIG:
            self._load_config(config_file)

        self._settings = settings
        self.custom = Config._flatten_config(dict(Config.CONFIG, **settings))

        if not self.custom:
            log.critical('No config values defined.  Aborting')
            sys.exit(1)

        self._initialize_attributes()

    def _fetch_or_not_set(self, key):
        if key in self._settings:
            return self._fetch(key)

        env_value = os.getenv(key)
        ini_value = self._fetch_deafult(key)

        if env_value is not None:
            return env_value
        elif ini_value is not None:
            return ini_value
        else:
            # This needs more thought. Return turning NoSet causes some database inserts to fail. I don't see an issue
            # using a straight None but I'm sure it will bite me in the ass
            return None
            #return self.CONFIG_NOT_SET

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
            'redis_database',
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
            'influx_token',
            'influx_org',
            'influx_bucket',
            'log_level',
            'index_current_max_age',
            'index_current_skip_load_age',
            'index_current_file',
            'index_meme_file',
            'index_meme_max_age',
            'index_meme_skip_load_age',
            'index_historical_skip_load_age',
            'index_historical_file',
            'index_historical_max_age',
            'default_hamming_distance',
            'repost_image_check_on_ingest',
            'repost_link_check_on_ingest',
            'enable_repost_watch',
            'image_hash_api',
            'summons_subreddits',
            'hot_post_comment_on_oc',
            'supported_post_types',
            'summons_match_strictness_loose',
            'summons_match_strictness_tight',
            'summons_all_matches',
            'summons_send_pm_subs',
            'summons_max_per_hour',
            'bot_comment_karma_flag_threshold',
            'bot_comment_karma_remove_threshold',
            'sub_monitor_exposed_config_options',
            'wiki_config_name',
            'index_api',
            'util_api',
            'live_responses',
            'top_post_offer_watch',
            'ocr_east_model',
            'ocr_min_confidence',
            'ocr_bounding_padding',
            'ocr_image_width',
            'ocr_image_height',
            'default_meme_filter_hash_size',
            'default_image_target_match',
            'default_image_target_meme_match',
            'default_image_target_title_match',
            'default_image_meme_filter',
            'default_image_target_annoy_distance',
            'default_image_max_matches',
            'default_image_same_sub_filter',
            'default_image_dead_matches_filter',
            'default_image_removed_match_filter',
            'default_image_only_older_matches',
            'default_image_same_author_filter',
            'default_image_crosspost_filter',
            'default_image_max_days_old_filter',
            'default_link_target_title_match',
            'default_link_same_sub_filter',
            'default_link_dead_matches_filter',
            'default_link_removed_match_filter',
            'default_link_only_older_matches',
            'default_link_same_author_filter',
            'default_link_crosspost_filter',
            'default_link_max_days_old_filter',
            'default_text_target_title_match',
            'default_text_same_sub_filter',
            'default_text_dead_matches_filter',
            'default_text_removed_match_filter',
            'default_text_only_older_matches',
            'default_text_same_author_filter',
            'default_text_crosspost_filter',
            'default_text_max_days_old_filter',
            'default_text_target_distance',
            'discord_logging_hook'

        ]

        for attribute in attrbs:
            setattr(self, attribute, self._fetch_or_not_set(attribute))


