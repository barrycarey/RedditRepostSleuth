import json

from falcon import Response, Request

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class ImageReposts:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, res: Response):
        results = []
        with self.uowm.start() as uow:
            reposts = uow.image_repost.get_all(limit=req.get_param_as_int('limit', default=100, required=False))
            for repost in reposts:
                result = {}
                result['repost'] = uow.posts.get_by_post_id(id=repost.post_id).to_dict()
                result['original'] = uow.posts.get_by_post_id(id=repost.repost_of).to_dict()
                result['percent'] = round(100 - (repost.hamming_distance / len(result['original']['dhash_h'])) * 100, 2)
                results.append(result)
            res.body = json.dumps(results)