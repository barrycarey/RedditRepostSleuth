import threading

# TODO - Mega hackery, figure this out.
import sys
from time import sleep

sys.path.append('./')
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.ingestsvc.postingestor import PostIngestor

if __name__ == '__main__':
    log.info('Starting post ingestor')
    print('Starting post ingestor')
    config = Config(r'C:\Users\mcare\PycharmProjects\RedditRepostSleuth\sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    ingestor = PostIngestor(get_reddit_instance(config), uowm)
    ingestor.ingest_without_stream()
    threading.Thread(target=ingestor.ingest_without_stream, name='praw_ingest').start()
    #threading.Thread(target=ingestor.ingest_pushshift, name='pushshift_ingest').start()

    while True:
        sleep(10)