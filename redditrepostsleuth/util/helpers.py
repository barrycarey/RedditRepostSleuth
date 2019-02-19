from influxdb import InfluxDBClient
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

def get_influx_instance() -> InfluxDBClient:
    return InfluxDBClient(
            config.influx_address,
            config.influx_port,
            database=config.influx_database,
            ssl=config.influx_ssl,
            verify_ssl=config.influx_verify_ssl,
            username=config.influx_user,
            password=config.influx_password,
            timeout=5,
            pool_size=50
        )

def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]