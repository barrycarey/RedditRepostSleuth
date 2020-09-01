import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class PostWatch:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, res: Response):
        response = {
            'data': [],
            'next_id': None
        }
        limit = req.get_param_as_int('limit', required=False, default=100)
        offset = req.get_param_as_int('offset', required=False)
        with self.uowm.start() as uow:
            watches = uow.repostwatch.get_all(limit=limit, offset=offset)
            for watch in watches:
                post = uow.posts.get_by_post_id(watch.post_id)
                response['data'].append({'watch': watch.to_dict(), 'post': post.to_dict()})

        res.body = json.dumps(response)

    def on_get_single(self):
        pass