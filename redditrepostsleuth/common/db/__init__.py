from sqlalchemy import create_engine

from redditrepostsleuth.common.config import config

db_engine = create_engine('mysql+pymysql://{}:{}@{}/{}'.format(config.db_user,
                                                                   config.db_password,
                                                                   config.db_host,
                                                                   config.db_name), echo=False, pool_size=50)
