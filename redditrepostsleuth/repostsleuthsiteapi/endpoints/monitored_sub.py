import json

from falcon import Response, Request, HTTP_NOT_FOUND

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class MonitoredSub:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        sub_name = req.get_param('subreddit', required=True)
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(sub_name)
            if not sub:
                resp.body = {}
                return
            resp.body = json.dumps(sub.to_dict())

    def on_post(self, req: Request, resp: Response):
        pass

    def on_put(self, req: Request, resp: Response):
        raw = json.loads(req.bounded_stream)
        print('')
