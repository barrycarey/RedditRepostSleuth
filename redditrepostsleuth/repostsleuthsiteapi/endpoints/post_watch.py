import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class PostWatch:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, res: Response):
        response = {
            'data': None,
            'next_id': None
        }
        limit = req.get_param_as_int('limit', required=False, default=100)
        offset = req.get_param_as_int('offset', required=False)
        with self.uowm.start() as uow:
            watches = uow.repostwatch.get_all(limit=limit, offset=offset)

        response['data'] = [watch.to_dict() for watch in watches]
        response['next_id'] = watches[-1].id + 1
        res.body = json.dumps(response)

    def on_get_single(self):
        pass