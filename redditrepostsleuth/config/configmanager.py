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

        self.delete_check_batch_size = self.config['GENERAL'].getint('delete_check_batch_size', fallback=50)

        self.subreddit_summons = self.config['GENERAL'].get('subreddit_summons', fallback='all')

        self.delete_check_batch_delay = self.config['GENERAL'].getint('delete_check_batch_delay', fallback=15)

        post_types = self.config['GENERAL'].get('supported_post_types', fallback='image')
        self.supported_post_types = post_types.split(',')

        # REPOST

        self.check_new_links_for_repost = self.config['REPOST'].getboolean('check_new_links_for_repost', fallback=False)
        self.repost_link_batch_size = self.config['REPOST'].getint('repost_link_batch_size', fallback=20)
        self.repost_link_batch_delay = self.config['REPOST'].getint('repost_link_batch_delay', fallback=20)

        self.check_new_images_for_repost = self.config['REPOST'].getboolean('check_new_images_for_repost', fallback=False)
        self.repost_image_batch_size = self.config['REPOST'].getint('repost_image_batch_size', fallback=20)
        self.repost_image_batch_delay = self.config['REPOST'].getint('repost_image_batch_delay', fallback=20)

        # IMAGES
        self.machine_id = self.config['IMAGES'].get('machine_id', fallback='1')
        self.index_tree_count = self.config['IMAGES'].getint('index_tree_count', fallback=20)
        self.index_keep_alive = self.config['IMAGES'].getint('index_keep_alive', fallback=20)
        self.index_file_name = self.config['IMAGES'].get('index_file_name', fallback='images.ann')
        self.annoy_match_cutoff = self.config['IMAGES'].getfloat('annoy_match_cutoff', fallback=0.25)
        self.hamming_cutoff = self.config['IMAGES'].getint('hamming_cutoff', fallback=8)
        self.annoy_total_neighbors = self.config['IMAGES'].getint('annoy_total_neighbors', fallback=50)
        self.index_build_lock_ttl = self.config['IMAGES'].getint('index_build_lock_ttl', fallback=300000)

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
        self.redis_host = self.config['CELERY']['redis_host']
        self.redis_password = self.config['CELERY']['redis_password']

        # InfluxDB
        self.influx_address = self.config['INFLUXDB']['Address']
        self.influx_port = self.config['INFLUXDB'].getint('Port', fallback=8086)
        self.influx_database = self.config['INFLUXDB'].get('Database', fallback='speedtests')
        self.influx_user = self.config['INFLUXDB'].get('Username', fallback='')
        self.influx_password = self.config['INFLUXDB'].get('Password', fallback='')
        self.influx_ssl = self.config['INFLUXDB'].getboolean('SSL', fallback=False)
        self.influx_verify_ssl = self.config['INFLUXDB'].getboolean('Verify_SSL', fallback=True)

        # Reddit
        self.reddit_praw_config = self.config['REDDIT'].getboolean('use_praw_config', fallback=False)
        self.reddit_client_id = self.config['REDDIT']['client_id']
        self.reddit_client_secret = self.config['REDDIT']['client_secret']
        self.reddit_useragent = self.config['REDDIT']['useragent']
        self.reddit_username = self.config['REDDIT']['username']
        self.reddit_password = self.config['REDDIT']['password']
