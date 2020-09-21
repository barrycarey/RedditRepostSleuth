import json

from falcon import Request, Response, HTTPNotFound, HTTPUnauthorized

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_user_data, is_sleuth_admin


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
                if not post:
                    continue
                response['data'].append({'watch': watch.to_dict(), 'post': post.to_dict()})

        res.body = json.dumps(response)

    def on_patch(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        data = json.load(req.bounded_stream)
        with self.uowm.start() as uow:
            watch = uow.repostwatch.get_by_id(data['id'])
            if not watch:
                raise HTTPNotFound(title=f'Post Watch Not Found',
                                   description=f'Unable to find post watch with ID {data["id"]}')
            if watch.user.lower() != user_data['name'].lower():
                if not is_sleuth_admin(token, user_data):
                    raise HTTPUnauthorized(title='You are not authorized to make this change',
                                           description='You are not authorized to modify this post watch')
            watch.enabled = data['enabled']
            uow.commit()

    def on_delete(self, req: Request, resp: Response):
        pass

    def on_post(self, req: Request, resp: Response):
        pass

    def on_get_single(self):
        pass