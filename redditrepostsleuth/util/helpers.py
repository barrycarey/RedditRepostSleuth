
from praw import Reddit

from redditrepostsleuth.config import config


def get_reddit_instance() -> Reddit:
    return Reddit(
                        client_id=config.reddit_client_id,
                        client_secret=config.reddit_client_secret,
                        password=config.reddit_password,
                        user_agent=config.reddit_useragent,
                        username=config.reddit_username
                    )

def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]