import os

import praw

from redditrepostsleuth.config.configmanager import ConfigManager

if os.getenv('SLEUTHCONFIG'):
    print('Config ENV Set')
    config = os.getenv('SLEUTHCONFIG')
else:
    config = 'testconfig.ini'

config = ConfigManager(config)

# TODO - Move this somewhere else
reddit = praw.Reddit(
        client_id=config.reddit_client_id,
        client_secret=config.reddit_client_secret,
        password=config.reddit_password,
        user_agent=config.reddit_useragent,
        username=config.reddit_username
    )