import sys
import threading
import time



sys.path.append('./')
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.adminsvc.inbox_monitor import InboxMonitor
from redditrepostsleuth.adminsvc.subreddit_config_update import SubredditConfigUpdater
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.adminsvc.new_activation_monitor import NewActivationMonitor
from redditrepostsleuth.adminsvc.stats_updater import StatsUpdater
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.adminsvc.bot_comment_monitor import BotCommentMonitor



if __name__ == '__main__':
    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    reddit_manager = RedditManager(get_reddit_instance(config))
    comment_monitor = BotCommentMonitor(reddit_manager, uowm, config)
    stats_updater = StatsUpdater()
    activation_monitor = NewActivationMonitor(uowm, get_reddit_instance(config))
    event_logger = EventLogging(config=config)
    response_handler = ResponseHandler(reddit_manager, uowm, event_logger)
    config_updater = SubredditConfigUpdater(uowm, reddit_manager.reddit, response_handler)
    inbox_monitor = InboxMonitor(uowm, reddit_manager.reddit)
    threading.Thread(target=config_updater.update_configs, name='config_update').start()
    threading.Thread(target=activation_monitor.check_for_new_invites, name='activation').start()
    while True:
        try:
            comment_monitor.check_comments()
            stats_updater.run_update()
            inbox_monitor.check_inbox()
            time.sleep(600)
        except Exception as e:
            log.exception('Admin svc died', exc_info=True)