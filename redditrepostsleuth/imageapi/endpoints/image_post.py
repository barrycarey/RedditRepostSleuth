import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class ImagePosts:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, res: Response):
        results = []
        with self.uowm.start() as uow:
            posts = uow.image_post.get_all(limit=req.get_param_as_int('limit', default=5, required=False))
            for post in posts:
                results.append(uow.posts.get_by_post_id(id=post.post_id).to_dict())
            res.body = json.dumps(results)