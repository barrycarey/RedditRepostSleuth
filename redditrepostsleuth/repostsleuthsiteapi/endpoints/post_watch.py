import json
from typing import Text

from falcon import Request, Response, HTTPNotFound, HTTPUnauthorized

from redditrepostsleuth.core.db.databasemodels import RepostWatch
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

    def on_get_user(self, req: Request, resp: Response, user: Text):
        results = []
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if user.lower() != user_data['name'].lower():
            if not is_sleuth_admin(token, user_data):
                raise HTTPUnauthorized(title='You are not authorized to views these watches',
                                       description=f'You are not authorized to view watches for {user}')
        with self.uowm.start() as uow:
            watches = uow.repostwatch.get_all_by_user(user_data['name'])
            for watch in watches:
                post = uow.posts.get_by_id(watch.post_id)
                if not post:
                    continue
                results.append({
                    'watch': watch.to_dict(),
                    'post': post.to_dict()
                })
        resp.body = json.dumps(results)

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
        token = req.get_param('token', required=True)
        watch_id = req.get_param_as_int('watch_id', required=True)
        user_data = get_user_data(token)
        with self.uowm.start() as uow:
            watch = uow.repostwatch.get_by_id(watch_id)
            if not watch:
                raise HTTPNotFound(title='No watch found', description=f'Failed to find watch with ID {watch_id}')
            if watch.user.lower() != user_data['name'].lower():
                if not is_sleuth_admin(token, user_data):
                    raise HTTPUnauthorized(title='You are not authorized to delete this watch',
                                           description='You are not authorized to delete this post watch')
            uow.repostwatch.remove(watch)
            uow.commit()


    def on_post(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        data = json.load(req.bounded_stream)
        with self.uowm.start() as uow:
            watch = RepostWatch(
                post_id=data['post_id'],
                user=user_data['name'],
                source='site'
            )
            uow.repostwatch.add(watch)
            uow.commit()

    def on_get_single(self):
        pass