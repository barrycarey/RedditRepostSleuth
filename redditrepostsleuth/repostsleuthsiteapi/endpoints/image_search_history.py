import json

from falcon import Request, Response, HTTPBadRequest

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log


class ImageSearchHistory:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get_search_history(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            post = uow.post.get_by_post_id(req.get_param('post_id'))
            if not post:
                raise HTTPBadRequest(title='Unable to find post', description=f'Cannot locate post with ID {req.get_param("post_id")}')
            results = uow.repost_search.get_by_post_id(post.id)
            resp.body = json.dumps([r.to_dict() for r in results])

    def on_get_monitored_sub_with_history(self, req: Request, resp: Response):
        results = []
        limit = req.get_param_as_int('limit', required=False, default=20)
        if limit == -1:
            limit = 1000
        with self.uowm.start() as uow:
            checked = uow.repost_search.get_by_subreddit(
                req.get_param('subreddit', required=True),
                limit=limit,
                offset=req.get_param_as_int('offset', required=False, default=None),
                only_reposts=req.get_param_as_bool('repost_only', required=False, default=False)
            )
            for search in checked:
                r = {
                    'checked_post': None,
                    'search': search.to_dict(),
                }
                post = uow.posts.get_by_post_id(search.post_id)

                results.append({
                    'checked_post': post.to_dict(),
                    'search': search.to_dict(),
                })
        resp.body = json.dumps(results)

    def on_get_monitored_sub_checked(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            results = uow.monitored_sub_checked.get_by_subreddit(
                req.get_param('subreddit', required=True),
                limit=req.get_param_as_int('limit', required=False, default=20),
                offset=req.get_param_as_int('offset', required=False, default=None)
            )
            resp.body = json.dumps([r.to_dict() for r in results])