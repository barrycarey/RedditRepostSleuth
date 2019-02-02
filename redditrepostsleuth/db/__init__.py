import os

from sqlalchemy import create_engine

db_engine = create_engine('mysql+pymysql://{}:{}@{}/{}'.format(os.getenv('DB_USER'),
                                                                   os.getenv('DB_PASS'),
                                                                   os.getenv('DB_HOST'),
                                                                   'reddit'))
