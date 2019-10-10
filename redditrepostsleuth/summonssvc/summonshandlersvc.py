import threading

from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler
from redditrepostsleuth.summonssvc.summonsmonitor import SummonsMonitor

uowm = SqlAlchemyUnitOfWorkManager(db_engine)
dup = DuplicateImageService(uowm)

summons = SummonsHandler(uowm, dup, get_reddit_instance())
summons.handle_summons()

with uowm.start() as uow:
    post = uow.posts.get_by_post_id('dg2foo')

result = dup.check_duplicate(post)

