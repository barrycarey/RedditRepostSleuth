import os

import praw

from redditrepostsleuth.config.configmanager import ConfigManager

if os.getenv('SLEUTHCONFIG'):
    print('Config ENV Set')
    config = os.getenv('SLEUTHCONFIG')
else:
    config = 'testconfig.ini'

config = ConfigManager(config)
