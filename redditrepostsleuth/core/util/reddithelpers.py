
from praw import Reddit

from redditrepostsleuth.core.config import Config


def get_reddit_instance(config: Config) -> Reddit:
    return Reddit(
                        client_id=config.reddit_client_id,
                        client_secret=config.reddit_client_secret,
                        password=config.reddit_password,
                        user_agent=config.reddit_useragent,
                        username=config.reddit_username
                    )