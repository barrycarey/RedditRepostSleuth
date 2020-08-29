import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log


class ImageSearchHistory:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get_search_history(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            results = uow.image_search.get_by_post_id(req.get_param('post_id', required=True))
            resp.body = json.dumps([r.to_dict() for r in results])

    def on_get_monitored_sub_with_history(self, req: Request, resp: Response):
        results = []
        limit = req.get_param_as_int('limit', required=False, default=20)
        if limit == -1:
            limit = 1000
        with self.uowm.start() as uow:
            checked = uow.monitored_sub_checked.get_by_subreddit(
                req.get_param('subreddit', required=True),
                limit=limit,
                offset=req.get_param_as_int('offset', required=False, default=None)
            )
            for p in checked:
                r = {
                    'checked_post': None,
                    'search': None,
                }
                post = uow.posts.get_by_post_id(p.post_id)
                searches = uow.image_search.get_by_post_id(p.post_id)
                submonitor_search = next((x for x in searches if x.source == 'sub_monitor'), None)

                if not submonitor_search:
                    log.error('Did not find search history for monitored sub checked post %s', p.post_id)
                    continue

                results.append({
                    'checked_post': post.to_dict(),
                    'search': submonitor_search.to_dict(),
                    'search_results': json.loads(submonitor_search.search_results)
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