import json
from typing import Text

from falcon import Response, Request, HTTPNotFound, HTTPUnauthorized, HTTPInternalServerError
from praw import Reddit
from praw.exceptions import APIException

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigChange
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.managed_subreddit import create_monitored_sub_in_db
from redditrepostsleuth.core.services.subreddit_config_updater import SubredditConfigUpdater
from redditrepostsleuth.core.util.default_bot_config import DEFAULT_CONFIG_VALUES
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod_token, get_user_data, get_subscribers, \
    is_sub_mod_praw, get_bot_permissions
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import is_site_admin


class MonitoredSub:
    def __init__(
            self,
            uowm: UnitOfWorkManager,
            config: Config,
            reddit: Reddit,
            config_updater: SubredditConfigUpdater
    ):
        self.config_updater = config_updater
        self.reddit = reddit
        self.config = config
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response, subreddit: Text):
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTPNotFound(title='Subreddit not found', description=f'{subreddit} is not registered')
            resp.body = json.dumps(sub.to_dict())

    def on_get_all(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            subs = uow.monitored_sub.get_all()
        resp.body = json.dumps([sub.to_dict() for sub in subs])

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

    def on_post_refresh(self, req: Request, resp: Response, subreddit: Text):
        log.info('Refreshing %s', subreddit)
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found',
                                   description=f'Subreddit {subreddit} Not Found')
            sub.subscribers = get_subscribers(sub.name, self.reddit)
            sub.is_mod = is_sub_mod_praw(sub.name, 'repostsleuthbot', self.reddit)
            perms = get_bot_permissions(sub.name, self.reddit) if sub.is_mod else []
            sub.post_permission = True if 'all' in perms or 'posts' in perms else None
            sub.wiki_permission = True if 'all' in perms or 'wiki' in perms else None
            uow.commit()
        resp.body = json.dumps(sub.to_dict())

    def on_post(self, req: Request, resp: Response, subreddit: Text):
        log.info('Attempting to create monitored sub %s', subreddit)
        token = req.get_param('token', required=True)
        if not is_sub_mod_token(token, subreddit, self.config.reddit_useragent):
            raise HTTPUnauthorized(f'You are not a moderator on {subreddit}',
                                   f'You\'re not a moderator on {subreddit}')
        try:
            self.reddit.subreddit(subreddit).mod.accept_invite()
        except APIException as e:
            if e.error_type == 'NO_INVITE_FOUND':
                log.error('No open invite to %s', subreddit)
                raise HTTPInternalServerError(f'No available invite for {subreddit}', f'We were unable to find a '
                                                                                      f'pending mod invote for r/{subreddit}')
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
        log.info('Saving settings for subreddit %s', subreddit)
        user_data = get_user_data(token)
        log.info('%s Save: Got user data', subreddit)
        if not is_sub_mod_token(token, subreddit, self.config.reddit_useragent):
            raise HTTPUnauthorized(f'Not authorized to make changes to {subreddit}', f'You\'re not a moderator on {subreddit}')
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            log.info('%s Save: Got sub data from database', subreddit)
            if not monitored_sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found', description=f'Subreddit {subreddit} Not Found')
            raw = json.load(req.bounded_stream)
            log.info('%s Save: Parsing config values', subreddit)
            for k,v in raw.items():
                log.info('%s Save: Key: %s | Value: %s', subreddit, k, v)
                if k not in self.config.sub_monitor_exposed_config_options:
                    continue
                if hasattr(monitored_sub, k):
                    if getattr(monitored_sub, k) != v:
                        log.debug('Update %s config | %s: %s => %s', subreddit, k, getattr(monitored_sub, k), v)
                        uow.monitored_sub_config_change.add(
                            MonitoredSubConfigChange(
                                source='site',
                                monitored_sub=monitored_sub,
                                config_key=k,
                                old_value=str(getattr(monitored_sub, k)),
                                new_value=str(v),
                                updated_by=user_data['name']
                            )
                        )
                        setattr(monitored_sub, k, v)
            try:
                log.info('%s Save: Saving config to DB', subreddit)
                uow.commit()
            except Exception as e:
                log.exception('Problem saving config', exc_info=True)
                raise HTTPInternalServerError(title='Problem Saving Config', description='Something went tits up when saving the config')

        celery.send_task('redditrepostsleuth.core.celery.admin_tasks.update_subreddit_config_from_database', args=[monitored_sub, user_data],
                         queue='update_wiki_from_database')




    def on_delete(self, req: Request, resp: Response, subreddit: Text):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not is_site_admin(user_data, self.uowm):
            raise HTTPUnauthorized(f'Not authorized to make this request',
                                   f'You are not authorized to make this request')
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTPNotFound(title=f'Subreddit {subreddit} Not Found',
                                   description=f'Subreddit {subreddit} Not Found')
            uow.monitored_sub.remove(sub)
            uow.commit()