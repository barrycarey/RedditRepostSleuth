import threading
import time
# TODO - Mega hackery, figure this out.
import sys
sys.path.append('./')
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.config import config
from redditrepostsleuth.core.db import db_engine
from redditrepostsleuth.summonssvc.summonsmonitor import SummonsMonitor




if __name__ == '__main__':
    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    summons = SummonsMonitor(get_reddit_instance(), uowm)
    threading.Thread(target=summons.monitor_for_mentions, name='mention_summons').start()
    threading.Thread(target=summons.monitor_for_summons_pushshift, name='pushshift_summons').start()
    threading.Thread(target=summons.monitor_for_summons, name='praw_summons', args=(config.subreddit_summons,)).start()
    #threading.Thread(target=summons.monitor_for_summons, name='praw_summons_all').start()

    while True:
        time.sleep(10)