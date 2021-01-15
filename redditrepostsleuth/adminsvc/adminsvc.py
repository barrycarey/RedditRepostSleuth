import sys
import time

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler

sys.path.append('./')
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.adminsvc.misc_admin_tasks import remove_expired_bans, update_banned_sub_wiki, \
    send_reports_to_meme_voting, update_top_image_reposts, \
    update_monitored_sub_data, check_meme_template_potential_votes, update_ban_list, queue_config_updates
from redditrepostsleuth.adminsvc.inbox_monitor import InboxMonitor
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

def event_callback(event):
    print(event)

if __name__ == '__main__':
    config = Config()
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    reddit = get_reddit_instance(config)
    reddit_manager = RedditManager(reddit)
    notification_svc = NotificationService(config)
    comment_monitor = BotCommentMonitor(reddit_manager, uowm, config, notification_svc=notification_svc)
    stats_updater = StatsUpdater()
    activation_monitor = NewActivationMonitor(uowm, get_reddit_instance(config), notification_svc=notification_svc)
    event_logger = EventLogging(config=config)
    response_handler = ResponseHandler(reddit_manager, uowm, event_logger)
    inbox_monitor = InboxMonitor(uowm, reddit_manager.reddit)

    #config_updater.update_configs()

    scheduler = BackgroundScheduler()
    scheduler.add_listener(event_callback, EVENT_JOB_ERROR)
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
        func=comment_monitor.check_comments,
        trigger='interval',
        minutes=30,
        name='comment_monitor',
        max_instances=1
    )
    scheduler.add_job(
        func=update_monitored_sub_data,
        args=(uowm,),
        trigger='interval',
        hours=6,
        name='updated_monitored_sub_data',
        max_instances=1
    )
    scheduler.add_job(
        func=remove_expired_bans,
        args=(uowm, notification_svc),
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
        name='updated_banned_subs',
        max_instances=1
    )
    scheduler.add_job(
        func=send_reports_to_meme_voting,
        args=(uowm,),
        trigger='interval',
        hours=1,
        name='send_reports_for_voting',
        max_instances=1
    )
    scheduler.add_job(
        func=update_top_image_reposts,
        args=(uowm,reddit),
        trigger='interval',
        days=1,
        name='update_image_reposts',
        max_instances=1
    )
    scheduler.add_job(
        func=check_meme_template_potential_votes,
        args=(uowm,),
        trigger='interval',
        minutes=30,
        name='check_meme_template_votes',
        max_instances=1
    )
    scheduler.add_job(
        func=update_ban_list,
        args=(uowm,notification_svc),
        trigger='interval',
        hours=24,
        name='check_banned_subs',
        max_instances=1
    )
    scheduler.add_job(
        func=queue_config_updates,
        args=(uowm, config),
        trigger='interval',
        minutes=2,
        name='queue_config_update_check',
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
