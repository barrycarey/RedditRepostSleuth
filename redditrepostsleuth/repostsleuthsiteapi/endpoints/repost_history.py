import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class RepostHistoryEndpoint:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        results = {
            'image': [],
            'link': []
        }
        with self.uowm.start() as uow:
            image_reposts = uow.image_repost.get_all_by_subreddit(
                req.get_param('subreddit', required=True),
                limit=req.get_param_as_int('limit', required=False, default=10),
                offset=req.get_param_as_int('offset', required=False)
            )
            link_reposts = uow.link_repost.get_all_by_subreddit(
                req.get_param('subreddit', required=True),
                limit=req.get_param_as_int('limit', required=False, default=10),
                offset=req.get_param_as_int('offset', required=False)
            )
            results['image'] = [p.to_dict() for p in image_reposts]
            results['link'] = [p.to_dict() for p in link_reposts]
            resp.body = json.dumps(results)

    def on_get_image_with_search(self, req: Request, resp: Response):
        results = []
        with self.uowm.start() as uow:
            searches = uow.image_search.get_all_reposts_by_subreddit(
                req.get_param('subreddit', required=True),
                limit=req.get_param_as_int('limit', required=False, default=10),
                offset=req.get_param_as_int('offset', required=False)
            )
            for search in searches:
                post = uow.posts.get_by_post_id(search.post_id)
                results.append({'checked_post': post.to_dict(), 'search': search.to_dict()})

        resp.body = json.dumps(results)

    def on_get_repost_image_feed(self, res: Request, resp: Response):
        results = []
        limit = res.get_param_as_int('limit', required=False, default=20)
        offset = res.get_param_as_int('offset', required=False)
        with self.uowm.start() as uow:
            reposts = uow.image_repost.get_all(limit=limit, offset=offset)
            for rp in reposts:
                post = uow.posts.get_by_post_id(rp.post_id)
                repost_of = uow.posts.get_by_post_id(rp.repost_of)
                search_data = uow.image_search.get_by_id(rp.search_id)
                if not post or not repost_of:
                    continue
                results.append({
                    'repost_data': rp.to_dict(),
                    'post': post.to_dict(),
                    'repost_of': repost_of.to_dict(),
                    'search_data': search_data.to_dict()})
        resp.body = json.dumps(results)