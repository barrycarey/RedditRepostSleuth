import os

from sqlalchemy import create_engine

db_engine = create_engine('mysql+pymysql://{}:{}@{}/{}'.format("dev",
                                                                   "@Password",
                                                                   "192.168.1.198",
                                                                   'reddit'))
