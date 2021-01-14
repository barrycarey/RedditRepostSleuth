from typing import NoReturn, Dict

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AdminTask
from redditrepostsleuth.core.db.databasemodels import MonitoredSub


@celery.task(bind=True, base=AdminTask)
def check_for_subreddit_config_update_task(self, monitored_sub: MonitoredSub) -> NoReturn:
    self.config_updater.check_for_config_update(monitored_sub, notify_missing_keys=False)

@celery.task(bind=True, base=AdminTask)
def update_subreddit_config_from_database(self, monitored_sub: MonitoredSub, user_data: Dict) -> NoReturn:
    self.config_updater.update_wiki_config_from_database(monitored_sub, notify=True)
    self.config_updater.notification_svc.send_notification(
        f'r/{monitored_sub.name} config updated on site by {user_data["name"]}',
        subject='**Config updated on repostsleuth.com**'
    )