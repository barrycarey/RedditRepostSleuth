import praw

from redditrepostsleuth.config import config


def get_reddit_instance():
    return praw.Reddit(
                        client_id=config.reddit_client_id,
                        client_secret=config.reddit_client_secret,
                        password=config.reddit_password,
                        user_agent=config.reddit_useragent,
                        username=config.reddit_username
                    )