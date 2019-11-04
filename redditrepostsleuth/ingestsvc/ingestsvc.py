import threading

# TODO - Mega hackery, figure this out.
import sys
sys.path.append('./')
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db import db_engine
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.ingestsvc.postingestor import PostIngestor

if __name__ == '__main__':
    log.info('Starting post ingestor')
    print('Starting post ingestor')
    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    ingestor = PostIngestor(get_reddit_instance(), uowm)

    threading.Thread(target=ingestor.ingest_without_stream, name='praw_ingest').start()
    threading.Thread(target=ingestor.ingest_pushshift, name='pushshift_ingest').start()