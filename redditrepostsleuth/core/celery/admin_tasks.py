from typing import NoReturn

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AdminTask
from redditrepostsleuth.core.db.databasemodels import MonitoredSub


@celery.task(bind=True, base=AdminTask)
def update_subreddit_config(self, monitored_sub: MonitoredSub) -> NoReturn:
    self.config_updater.check_for_config_update(monitored_sub, notify_missing_keys=False)