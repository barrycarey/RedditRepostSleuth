import threading

# TODO - Mega hackery, figure this out.
import os,sys
sys.path.append('./')
from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.ingestsvc.postingestor import PostIngestor

if __name__ == '__main__':
    log.info('Starting post ingestor')
    print('Starting post ingestor')
    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    ingestor = PostIngestor(get_reddit_instance(), uowm)
    threading.Thread(target=ingestor.ingest_new_posts, name='praw_ingest').start()
    #threading.Thread(target=ingestor.ingest_pushshift, name='pushshift_ingest').start()