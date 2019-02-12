import configparser
import os
import sys


class ConfigManager:
    def __init__(self, config):

        print('Loading config: ' + config)
        print(os.getcwd())

        config_file = os.path.join(os.getcwd(), config)
        if os.path.isfile(config_file):
            self.config = configparser.ConfigParser()
            self.config.read(config_file)
        else:
            print('ERROR: Unable To Load Config File: {}'.format(config_file))
            sys.exit(1)

        self._load_config_values()

        print('Configuration Successfully Loaded')

    def _load_config_values(self):

        # General
        self.summon_command = self.config['GENERAL'].get('summon_command', fallback='!repost')
        self.generate_hash_batch_size = self.config['GENERAL'].getint('generate_hash_batch_size', fallback=50)
        self.delete_check_batch_size = self.config['GENERAL'].getint('delete_check_batch_size', fallback=50)
        self.vptree_cache_duration = self.config['GENERAL'].getint('vptree_cache_duration', fallback=1800)
        self.hamming_distance = self.config['GENERAL'].getint('hamming_distance', fallback=10)
        self.subreddit_summons = self.config['GENERAL'].get('subreddit_summons', fallback='all')
        self.check_repost_on_ingest = self.config['GENERAL'].getboolean('check_repost_on_ingest', fallback=False)
        self.generate_hash_batch_delay = self.config['GENERAL'].getint('generate_hash_batch_delay', fallback=15)
        self.delete_check_batch_delay = self.config['GENERAL'].getint('delete_check_batch_delay', fallback=15)
        self.check_repost_batch_size = self.config['GENERAL'].getint('check_repost_batch_size', fallback=2)
        self.check_repost_batch_delay = self.config['GENERAL'].getint('check_repost_batch_delay', fallback=20)
        self.link_repost_batch_size = self.config['GENERAL'].getint('link_repost_batch_size', fallback=20)
        self.link_repost_batch_delay = self.config['GENERAL'].getint('link_repost_batch_delay', fallback=20)
        post_types = self.config['GENERAL'].get('supported_post_types', fallback='image')
        self.supported_post_types = post_types.split(',')

        # Database
        self.db_host = self.config['DATABASE']['host']
        self.db_port = self.config['DATABASE'].getint('port', fallback=3306)
        self.db_name = self.config['DATABASE']['name']
        self.db_user = self.config['DATABASE']['user']
        self.db_password = self.config['DATABASE']['password']


        # Logging
        self.log_level = self.config['LOGGING'].get('level', fallback='INFO').upper()
        self.log_file = self.config['LOGGING']['log_file']
        self.log_file_level = self.config['LOGGING']['log_file_level']

        # CELERY
        self.celery_broker = self.config['CELERY']['broker']
        self.celery_backend = self.config['CELERY']['backend']

        # Reddit
        self.reddit_praw_config = self.config['REDDIT'].getboolean('use_praw_config', fallback=False)
        self.reddit_client_id = self.config['REDDIT']['client_id']
        self.reddit_client_secret = self.config['REDDIT']['client_secret']
        self.reddit_useragent = self.config['REDDIT']['useragent']
        self.reddit_username = self.config['REDDIT']['username']
        self.reddit_password = self.config['REDDIT']['password']