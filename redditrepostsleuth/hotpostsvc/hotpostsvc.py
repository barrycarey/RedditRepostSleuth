import threading

from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.hotpostsvc.toppostmonitor import TopPostMonitor
from redditrepostsleuth.summonssvc.summonsmonitor import SummonsMonitor

red = get_reddit_instance()


uowm = SqlAlchemyUnitOfWorkManager(db_engine)
top = TopPostMonitor(get_reddit_instance(), uowm)
top.monitor()
#summons.monitor_for_summons()