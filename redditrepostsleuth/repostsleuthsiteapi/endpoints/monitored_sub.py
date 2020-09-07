import json
from typing import Text

import requests
from falcon import Response, Request, HTTP_NOT_FOUND, HTTPNotFound, HTTPUnauthorized, HTTPInternalServerError
from praw import Reddit
from praw.exceptions import APIException

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.managed_subreddit import create_monitored_sub_in_db

import logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
class MonitoredSub:
    def __init__(self, uowm: UnitOfWorkManager, config: Config, reddit: Reddit):
        self.reddit = reddit
        self.config = config
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response, subreddit: Text):
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                resp.body = {}
                return
            resp.body = json.dumps(sub.to_dict())

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
        #if not self.is_sleuth_admin(token):
        if not self.is_sub_mod(token, subreddit):
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
                        setattr(sub, k, v)
            #uow.commit()

    def check_mod_status(self, token: Text):
        headers = {'Authorization': f'Bearer {token}'}

    def get_user_data(self, token):
        headers = {'Authorization': f'Bearer {token}', 'User-Agent': self.config.reddit_useragent}
        r = requests.get('https://oauth.reddit.com/api/v1/me/', headers=headers)
        if r.status_code != 200:
            return
        return json.loads(r.text)

    def is_sleuth_admin(self, token):
        user_data = self.get_user_data(token)
        if not user_data:
            log.error('Failed to get user data')
            return False
        headers = {'Authorization': f'Bearer {token}', 'User-Agent': self.config.reddit_useragent}
        r = requests.get('https://oauth.reddit.com/r/repostsleuthbot/about/moderators', headers=headers)
        if r.status_code != 200:
            log.error('Failed to get moderator list from %s', 'RepostSleuthBot')
            return False

        raw_data = json.loads(r.text)
        for mod in raw_data['data']['children']:
            if mod['name'].lower() == user_data['name'].lower():
                return True

        return False

    def is_sub_mod(self, token, subreddit):
        headers = {'Authorization': f'Bearer {token}', 'User-Agent': self.config.reddit_useragent}
        after = None
        while True:
            url = 'https://oauth.reddit.com/subreddits/mine/moderator?limit=100'
            if after:
                url += f'&after={after}'
            r = requests.get(url, headers=headers)

            data = json.loads(r.text)
            subs = data['data']['children']
            if not subs:
                break
            after = subs[-1]['data']['name']
            for sub in subs:
                if sub['data']['display_name'].lower() == subreddit.lower():
                    return True
        return False