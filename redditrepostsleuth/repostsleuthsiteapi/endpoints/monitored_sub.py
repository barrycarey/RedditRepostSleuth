import json
from typing import Text

from falcon import Response, Request, HTTP_NOT_FOUND

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class MonitoredSub:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response, subreddit: Text):
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                resp.body = {}
                return
            resp.body = json.dumps(sub.to_dict())

    def on_post(self, req: Request, resp: Response):
        pass

    def on_put(self, req: Request, resp: Response, subreddit: Text):
        token = req.get_param('token', required=True)
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTP_NOT_FOUND(f'Subreddit {subreddit} Not Found', f'Subreddit {subreddit} Not Found')
            raw = json.load(req.bounded_stream)
            for k,v in raw.items():
                if hasattr(sub, k):
                    setattr(sub, k, v)
            uow.commit()

    def check_mod_status(self, token: Text):
        headers = {'Authorization': f'Bearer {token}'}

    def is_sleuth_admin(self, token):
        pass