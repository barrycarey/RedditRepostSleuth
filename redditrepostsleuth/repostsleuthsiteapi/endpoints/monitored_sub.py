import json
from typing import Text

import requests
from falcon import Response, Request, HTTP_NOT_FOUND, HTTPNotFound, HTTPUnauthorized, HTTPInternalServerError
from praw import Reddit
from praw.exceptions import APIException

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigChange
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.managed_subreddit import create_monitored_sub_in_db

import logging

from redditrepostsleuth.core.util.default_bot_config import DEFAULT_CONFIG_VALUES
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod, get_user_data


class MonitoredSub:
    def __init__(self, uowm: UnitOfWorkManager, config: Config, reddit: Reddit):
        self.reddit = reddit
        self.config = config
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response, subreddit: Text):
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                resp.body = json.dumps({})
                return
            resp.body = json.dumps(sub.to_dict())

    def on_get_popular(self, req: Request, resp: Response):
        results = []
        with self.uowm.start() as uow:
            subs = uow.monitored_sub.get_all_active(limit=10)
            for sub in subs:
                results.append({
                    'name': sub.name,
                    'subscribers': sub.subscribers
                })
            resp.body = json.dumps(results)

    def on_get_default_config(self, req: Request, resp: Response):
        resp.body = json.dumps(DEFAULT_CONFIG_VALUES)

    def on_post(self, req: Request, resp: Response, subreddit: Text):
        log.info('Attempting to create monitored sub %s', subreddit)
        try:
            self.reddit.subreddit(subreddit).mod.accept_invite()
        except APIException as e:
            if e.error_type == 'NO_INVITE_FOUND':
                log.error('No open invite to %s', subreddit)
                raise HTTPInternalServerError(f'No available invite for {subreddit}', f'We were unable to find a pending mod invote for r/{subreddit}')
            else:
                log.exception('Problem accepting invite', exc_info=True)
                raise HTTPInternalServerError(f'Unknown error accepting mod invite for r/{subreddit}', f'Unknown error accepting mod invite for r/{subreddit}.  Please contact us')
        except Exception as e:
            log.exception('Failed to accept invite', exc_info=True)
            raise HTTPInternalServerError(f'Unknown error accepting mod invite for r/{subreddit}', f'Unknown error accepting mod invite for r/{subreddit}.  Please contact us')

        with self.uowm.start() as uow:
            existing = uow.monitored_sub.get_by_sub(subreddit)
            if existing:
                resp.body = json.dumps(existing.to_dict())
                return
            monitored_sub = create_monitored_sub_in_db(subreddit, uow)
            resp.body = json.dumps(monitored_sub.to_dict())


    def on_patch(self, req: Request, resp: Response, subreddit: Text):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not is_sub_mod(token, subreddit, self.config.reddit_useragent):
            raise HTTPUnauthorized(f'Not authorized to make changes to {subreddit}', f'You\'re not a moderator on {subreddit}')
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found', description=f'Subreddit {subreddit} Not Found')
            raw = json.load(req.bounded_stream)
            for k,v in raw.items():
                if k not in self.config.sub_monitor_exposed_config_options:
                    continue
                if hasattr(sub, k):
                    if getattr(sub, k) != v:
                        log.debug('Update %s config | %s: %s => %s', subreddit, k, getattr(sub, k), v)
                        uow.monitored_sub_config_change.add(
                            MonitoredSubConfigChange(
                                source='site',
                                subreddit=subreddit,
                                config_key=k,
                                old_value=str(getattr(sub, k)),
                                new_value=str(v),
                                updated_by=user_data['name']
                            )
                        )
                        setattr(sub, k, v)
            uow.commit()

