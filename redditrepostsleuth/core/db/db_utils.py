from sqlalchemy import create_engine

from redditrepostsleuth.core.config import config

def get_db_engine():
    return create_engine('mysql+pymysql://{}:{}@{}/{}'.format(config.db_user,
                                                                   config.db_password,
                                                                   config.db_host,
                                                                   config.db_name), echo=False, pool_size=50)

