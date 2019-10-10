import threading

from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.summonssvc.summonsmonitor import SummonsMonitor

uowm = SqlAlchemyUnitOfWorkManager(db_engine)
summons = SummonsMonitor(get_reddit_instance(), uowm)
#summons.monitor_for_summons()
threading.Thread(target=summons.monitor_for_summons_pushshift, name='praw_ingest').start()
threading.Thread(target=summons.monitor_for_summons, name='pushshift_ingest').start()