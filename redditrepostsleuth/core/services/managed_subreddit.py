from typing import Text

from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.default_bot_config import DEFAULT_CONFIG_VALUES


def create_monitored_sub_in_db(subreddit_name: Text, uow: UnitOfWork, wiki_managed: bool = False) -> MonitoredSub:

    monitored_sub = MonitoredSub(name=subreddit_name)
    for k,v in DEFAULT_CONFIG_VALUES.items():
        if hasattr(monitored_sub, k):
            setattr(monitored_sub, k, v)
    monitored_sub.wiki_managed = wiki_managed
    uow.monitored_sub.add(monitored_sub)
    try:
        uow.commit()
        log.info('Sub %s added as monitored sub', subreddit_name)
    except IntegrityError as e:
        # TODO - This can be pulled since we're checking during activation
        log.error('Failed to create monitored sub for %s.  It already exists', subreddit_name, exc_info=True)
    except Exception as e:
        log.exception('Unknown exception saving monitored sub', exc_info=True)
        raise

    return monitored_sub