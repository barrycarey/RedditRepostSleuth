import sys
import time

from redditrepostsleuth.adminsvc.stats_updater import StatsUpdater
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.adminsvc.bot_comment_monitor import BotCommentMonitor

sys.path.append('./')

if __name__ == '__main__':
    while True:
        config = Config()
        uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
        reddit_manager = RedditManager(get_reddit_instance(config))
        comment_monitor = BotCommentMonitor(reddit_manager, uowm, config)
        comment_monitor.check_comments()
        stats_updater = StatsUpdater()
        stats_updater.run_update()
        time.sleep(1800)