import threading
import time

import sys
# TODO - Mega hackery, figure this out.
sys.path.append('./')
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.summonssvc.summonsmonitor import SummonsMonitor


if __name__ == '__main__':
    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    summons = SummonsMonitor(get_reddit_instance(config), uowm, config)
    threading.Thread(target=summons.monitor_for_mentions, name='mention_summons').start()
    #threading.Thread(target=summons.monitor_for_summons_pushshift, name='pushshift_summons').start()
    #threading.Thread(target=summons.monitor_for_summons, name='praw_summons', args=(config.summons_subreddits,)).start()
    #threading.Thread(target=summons.monitor_for_summons, name='praw_summons_all').start()

    while True:
        time.sleep(10)