import os

from redditrepostsleuth.core.config.configmanager import ConfigManager

if os.getenv('SLEUTHCONFIG'):
    print('Config ENV Set')
    config = os.getenv('SLEUTHCONFIG')
else:
    config = '/home/barry/PycharmProjects/RedditRepostSleuth/testconfig.ini'

config = ConfigManager(config)
