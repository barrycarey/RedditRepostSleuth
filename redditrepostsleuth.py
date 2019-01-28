import praw
import os

from sqlalchemy import create_engine

from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.service.postIngest import PostIngest

reddit = praw.Reddit(
    client_id=os.getenv('redditclientid'),
    client_secret=os.getenv('redditsecret'),
    password=os.getenv('redditpass'),
    user_agent='testscript by /u/fakebot3',
    username=os.getenv('reddituser')
)

db_engine = create_engine('mysql+pymysql://{}:{}@{}/{}'.format(os.getenv('DB_USER'),
                                                               os.getenv('DB_PASS'),
                                                               os.getenv('DB_HOST'),
                                                               'reddit'))

ingest = PostIngest(reddit, SqlAlchemyUnitOfWorkManager(db_engine))
ingest.run()