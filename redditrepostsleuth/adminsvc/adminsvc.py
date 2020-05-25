import sys
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler



sys.path.append('./')
from redditrepostsleuth.adminsvc.misc_admin_tasks import update_mod_status, update_monitored_sub_subscribers, \
    remove_expired_bans, update_banned_sub_wiki
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
    reddit = get_reddit_instance(config)
    reddit_manager = RedditManager(reddit)
    comment_monitor = BotCommentMonitor(reddit_manager, uowm, config)
    stats_updater = StatsUpdater()
    activation_monitor = NewActivationMonitor(uowm, get_reddit_instance(config))
    event_logger = EventLogging(config=config)
    response_handler = ResponseHandler(reddit_manager, uowm, event_logger)
    config_updater = SubredditConfigUpdater(uowm, reddit_manager.reddit, response_handler, config)
    inbox_monitor = InboxMonitor(uowm, reddit_manager.reddit)

    config_updater.update_configs()

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=config_updater.update_configs,
        trigger='interval',
        minutes=15,
        name='update_configs',
        max_instances=3
    )
    scheduler.add_job(
        func=activation_monitor.check_for_new_invites,
        trigger='interval',
        minutes=1,
        name='activation_checker',
        max_instances=1
    )
    scheduler.add_job(
        func=stats_updater.run_update,
        trigger='interval',
        minutes=15,
        name='stats_update',
        max_instances=1
    )
    scheduler.add_job(
        func=inbox_monitor.check_inbox,
        trigger='interval',
        minutes=5,
        name='inbox_monitor',
        max_instances=1
    )
    scheduler.add_job(
        func=update_mod_status,
        args=(uowm, reddit_manager),
        trigger='interval',
        minutes=20,
        name='check_mod_status',
        max_instances=1
    )
    scheduler.add_job(
        func=update_monitored_sub_subscribers,
        args=(uowm, reddit_manager),
        trigger='interval',
        hours=6,
        name='update_subscriber_count',
        max_instances=1
    )
    scheduler.add_job(
        func=remove_expired_bans,
        args=(uowm,),
        trigger='interval',
        minutes=5,
        name='remove_expired_bans',
        max_instances=1
    )
    scheduler.add_job(
        func=update_banned_sub_wiki,
        args=(uowm, reddit),
        trigger='interval',
        hours=1,
        name='update_subscriber_count',
        max_instances=1
    )
    scheduler.start()
    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        # Not strictly necessary if daemonic mode is enabled but should be done if possible
        scheduler.shutdown()
