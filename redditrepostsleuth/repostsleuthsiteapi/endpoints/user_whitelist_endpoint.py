import json
import logging

from falcon import Request, Response, HTTPUnauthorized, HTTPNotFound, HTTPBadRequest
from praw import Reddit

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import UserWhitelist
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod_token

log = logging.getLogger(__name__)
class UserWhitelistEndpoint:
    def __init__(
            self,
            uowm: UnitOfWorkManager,
            config: Config,
            reddit: Reddit
    ):
        self.reddit = reddit
        self.config = config
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response, subreddit: str):
        token = req.get_param('token', required=True)
        if not is_sub_mod_token(token, subreddit, self.config.reddit_useragent):
            raise HTTPUnauthorized(f'You are not a moderator on {subreddit}',
                                   f'You\'re not a moderator on {subreddit}')

        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            if not monitored_sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found', description=f'Subreddit {subreddit} Not Found')


            resp.body = json.dumps([u.to_dict() for u in monitored_sub.user_whitelist])

    def on_post(self, req: Request, resp: Response, subreddit: str):
        token = req.get_param('token', required=True)
        user_json = json.load(req.bounded_stream)
        if not is_sub_mod_token(token, subreddit, self.config.reddit_useragent):
            raise HTTPUnauthorized(f'Not authorized to make changes to {subreddit}', f'You\'re not a moderator on {subreddit}')

        if 'username' not in user_json:
            log.error('No username included for new user whitelist')
            raise HTTPBadRequest(title='Missing username in whitelist data', description='Missing username in whitelist data')

        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            if not monitored_sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found', description=f'Subreddit {subreddit} Not Found')

            existing_whitelist = uow.user_whitelist.get_by_username_and_subreddit(user_json['username'], monitored_sub.id)
            if existing_whitelist:
                raise HTTPBadRequest(title='User already whitelisted',
                                     description=f'User {user_json["username"]} already whitelisted on {subreddit}')


            user_whitelist = UserWhitelist()
            user_whitelist.monitored_sub_id = monitored_sub.id
            for k, v in user_json.items():
                if hasattr(user_whitelist, k):
                    log.debug('Setting %s to %s', k, v)
                    setattr(user_whitelist, k, v)

            monitored_sub.user_whitelist.append(user_whitelist)
            uow.commit()

            resp.text = json.dumps(user_whitelist.to_dict())

    def on_patch(self, req: Request, resp: Response, subreddit: str):
        token = req.get_param('token', required=True)
        user_json = json.load(req.bounded_stream)
        if not is_sub_mod_token(token, subreddit, self.config.reddit_useragent):
            raise HTTPUnauthorized(f'Not authorized to make changes to {subreddit}',
                                   f'You\'re not a moderator on {subreddit}')

        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            if not monitored_sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found',
                                   description=f'Subreddit {subreddit} Not Found')

            existing_whitelist = uow.user_whitelist.get_by_username_and_subreddit(user_json['username'],
                                                                                  monitored_sub.id)
            if not existing_whitelist:
                raise HTTPBadRequest(title='Nothing to modify',
                                     description=f'User {user_json["username"]} does not have an existing whitelist in {subreddit}')

            for k, v in user_json.items():
                if hasattr(existing_whitelist, k):
                    log.debug('Setting %s to %s', k, v)
                    setattr(existing_whitelist, k, v)

            uow.commit()

            resp.text = json.dumps(existing_whitelist.to_dict())

    def on_delete(self, req: Request, resp: Response, subreddit: str):
        token = req.get_param('token', required=True)
        id_to_delete = req.get_param_as_int('id', required=True)
        if not is_sub_mod_token(token, subreddit, self.config.reddit_useragent):
            raise HTTPUnauthorized(f'Not authorized to make changes to {subreddit}',
                                   f'You\'re not a moderator on {subreddit}')

        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            if not monitored_sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found',
                                   description=f'Subreddit {subreddit} Not Found')

            existing_whitelist = uow.user_whitelist.get_by_id(id_to_delete)
            if not existing_whitelist:
                raise HTTPNotFound(title=f'Cannot find whitelist with ID {id_to_delete}',
                                   description=f'Cannot find whitelist with ID {id_to_delete}')

            uow.user_whitelist.remove(existing_whitelist)
            uow.commit()