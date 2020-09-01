import json

from falcon import Request, Response, HTTPNotFound

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class ImageRepostEndpoint:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            post = uow.posts.get_by_post_id(req.get_param('post_id', required=True))
            if not post:
                raise HTTPNotFound('Post not found', f'This post was not found in the Repost Sleuth Database')
            resp.body = json.dumps(post.to_dict())
