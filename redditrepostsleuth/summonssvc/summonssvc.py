import threading

from redditrepostsleuth.common.config import config
from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.summonssvc.summonsmonitor import SummonsMonitor

red = get_reddit_instance()


uowm = SqlAlchemyUnitOfWorkManager(db_engine)
summons = SummonsMonitor(get_reddit_instance(), uowm, config.subreddit_summons)
summons_all = SummonsMonitor(get_reddit_instance(), uowm, 'all')
#summons.monitor_for_summons()
threading.Thread(target=summons.monitor_for_summons_pushshift, name='pushshift_summons').start()
threading.Thread(target=summons.monitor_for_summons, name='praw_summons').start()
threading.Thread(target=summons_all.monitor_for_summons, name='praw_summons_all').start()